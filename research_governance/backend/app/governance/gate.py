# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""The governance gate — the heart of GovDesk.

Every agent action flows through :func:`evaluate`. For each action we:

1. **Evaluate** it against the agent's policy with AGT ``PolicyEngine``
   (deterministic allow / deny / require_approval). FEATURES.md: *Policy engine*.
2. **Audit** the decision into a hash-chained ``AuditLog`` and persist the
   entry. FEATURES.md: *Audit + Merkle chain*.
3. **Score** the agent: feed a policy-compliance signal to ``RewardEngine`` and
   update its stored trust score/tier; auto-suspend on collapse.
   FEATURES.md: *Trust scoring*.
4. **Persist + broadcast** the decision so the React Governance page can show
   the complete history live.

This module holds the single source of truth for governance state in the
process. It is deliberately framework-agnostic: the LangGraph nodes call
``evaluate`` and act on the returned :class:`Verdict`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

import app.config  # noqa: F401  (AGT import bootstrap)
from agentmesh.governance.audit import AuditLog
from agentmesh.governance.policy import PolicyEngine
from agentmesh.reward.engine import RewardEngine
from agentmesh.reward.scoring import DimensionType

from app.config import settings
from app.governance.identities import GovAgent, all_agents, get_agent
from app.store import db

_POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"

# Verdict -> policy-compliance signal (0 bad .. 1 good) fed to the trust engine.
_COMPLIANCE_SIGNAL = {
    "allow": 1.0,
    "log": 0.9,
    "warn": 0.6,
    "require_approval": 0.5,
    "deny": 0.0,
}

# Below this stored trust score an agent is auto-suspended (demo threshold).
_SUSPEND_BELOW = 250


@dataclass
class Verdict:
    """Normalized result of a governed action."""

    allowed: bool
    action_type: str
    verdict: str                 # allow | deny | require_approval | warn | log
    matched_rule: str | None
    policy_name: str | None
    reason: str
    latency_ms: float
    agent_did: str
    agent_name: str
    requires_approval: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# Listeners for live decision streaming (the WebSocket layer registers here).
_Listener = Callable[[dict], None]


class GovernanceGate:
    """Process-wide governance state: engines per agent + shared audit/trust."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._engines: dict[str, PolicyEngine] = {}      # agent key -> engine
        self._audit = AuditLog()                          # shared hash chain
        self._reward = RewardEngine()                     # shared trust engine
        self._listeners: list[_Listener] = []
        self._ready = False

    # -- lifecycle ---------------------------------------------------------
    def setup(self) -> None:
        """Load every agent's policy and seed trust. Idempotent."""
        with self._lock:
            if self._ready:
                return
            db.init_db()
            # Agent identities are minted fresh each process, so start from a
            # clean store: the roster, rings, decisions, audit, trust, and
            # runtime events all reference this process's DIDs. (Durable
            # cross-restart history would require stable identities — a later
            # enhancement.)
            db.reset_db()
            # Screen the MCP tool catalog up front so the Market-Data agent
            # can only ever use tools that passed security scanning.
            try:
                from app.governance.mcp_security import mcp_security

                mcp_security.scan_catalog()
            except Exception:
                logger.warning("MCP catalog scan failed at setup", exc_info=True)
            # Vet MCP tools as marketplace plugins (depends on the MCP scan
            # above so a blocked tool is forced to the revoked tier).
            try:
                from app.governance.marketplace import marketplace

                marketplace.vet_catalog()
            except Exception:
                logger.warning("marketplace vetting failed at setup", exc_info=True)
            # Register every agent with the kill switch and stamp its ring.
            try:
                from app.governance.killswitch import killswitch
                from app.governance.rings import rings as _rings

                for a in all_agents():
                    killswitch.register(a.did)
                    db.upsert_agent(
                        did=a.did, name=a.name, role=a.role,
                        ring=_rings.ring_label(a.key), capabilities=a.capabilities,
                    )
            except Exception:
                logger.warning("kill-switch/ring registration failed at setup", exc_info=True)

            for agent in all_agents():
                engine = PolicyEngine(conflict_strategy="deny_overrides")
                policy_path = _POLICY_DIR / agent.policy_file
                engine.load_yaml(policy_path.read_text(encoding="utf-8"))
                self._engines[agent.key] = engine
                # Seed a neutral-positive trust signal so the score is real.
                self._reward.record_signal(
                    agent.did, DimensionType.POLICY_COMPLIANCE, 1.0, source="bootstrap"
                )
                self._sync_trust(agent.did)

            # Shadow discovery: reconcile observed agents against the registry.
            try:
                from app.governance.discovery import discovery

                discovery.scan()
            except Exception:
                logger.warning("shadow discovery failed at setup", exc_info=True)

            self._ready = True

    # -- listeners ---------------------------------------------------------
    def add_listener(self, fn: _Listener) -> None:
        with self._lock:
            self._listeners.append(fn)

    def remove_listener(self, fn: _Listener) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def _broadcast(self, payload: dict) -> None:
        for fn in list(self._listeners):
            try:
                fn(payload)
            except Exception:
                pass  # a broken listener must not break governance

    # -- core evaluate -----------------------------------------------------
    def evaluate(
        self,
        agent_key: str,
        action: dict[str, Any],
        *,
        run_id: str | None = None,
        resource: str | None = None,
        signals: dict[str, Any] | None = None,
    ) -> Verdict:
        """Evaluate one action for one agent; audit, score, persist, broadcast.

        ``signals`` carries soft context (e.g. research sentiment, price
        momentum) that the probabilistic advisory layer may consider. It is
        NOT used by the deterministic policy engine.
        """
        if not self._ready:
            self.setup()

        agent: GovAgent = get_agent(agent_key)
        engine = self._engines[agent.key]
        action_type = str(action.get("type", "unknown"))

        start = time.perf_counter()
        decision = engine.evaluate(agent.did, {"action": action})
        latency_ms = (time.perf_counter() - start) * 1000

        # --- Advisory layer -------------------------------------------------
        # Runs ONLY after a deterministic allow, and may only tighten it. A
        # block downgrades the allow to a deny; a flag keeps the allow but is
        # recorded. The advisory can never turn a deny into an allow.
        advisory_action = advisory_confidence = advisory_reason = advisory_classifier = None
        effective_action = decision.action
        effective_reason = decision.reason
        if decision.action == "allow":
            adv = self._run_advisory(action, signals)
            if adv is not None:
                advisory_action = adv.action
                advisory_confidence = round(adv.confidence, 3)
                advisory_reason = adv.reason
                advisory_classifier = adv.classifier
                if adv.action == "block":
                    effective_action = "deny"
                    effective_reason = f"[advisory, non-deterministic] {adv.reason}"
                elif adv.action == "flag_for_review":
                    effective_reason = (
                        f"{decision.reason or 'allowed'} "
                        f"(advisory flag: {adv.reason})"
                    )

        requires_approval = effective_action == "require_approval"
        allowed = effective_action == "allow"

        # 1) Audit (hash-chained) + persist the entry
        outcome = "success" if allowed else ("denied" if effective_action == "deny" else effective_action)
        entry = self._audit.log(
            event_type="policy_evaluation",
            agent_did=agent.did,
            action=action_type,
            resource=resource,
            outcome=outcome,
            policy_decision=effective_action,
            data={
                "rule": decision.matched_rule or "",
                "reason": effective_reason or "",
                "policy": decision.policy_name or "",
                "latency_ms": round(latency_ms, 3),
                **({"advisory": advisory_action, "advisory_confidence": advisory_confidence}
                   if advisory_action else {}),
            },
        )
        db.add_audit_entry(
            entry_id=entry.entry_id,
            agent_did=agent.did,
            action=action_type,
            outcome=outcome,
            resource=resource,
            policy_decision=effective_action,
            entry_hash=entry.entry_hash,
            previous_hash=entry.previous_hash,
            data={"rule": decision.matched_rule, "reason": effective_reason,
                  "advisory": advisory_action},
        )

        # 2) Trust signal + sync stored score (uses the EFFECTIVE outcome)
        self._reward.record_signal(
            agent.did,
            DimensionType.POLICY_COMPLIANCE,
            _COMPLIANCE_SIGNAL.get(effective_action, 0.5),
            source="policy_engine",
            details=f"{action_type} -> {effective_action}",
        )
        self._sync_trust(agent.did)

        # 3) Persist the decision
        dec_rec = db.add_decision(
            agent_did=agent.did,
            agent_name=agent.name,
            action=action_type,
            verdict=effective_action,
            run_id=run_id,
            resource=resource,
            matched_rule=decision.matched_rule,
            policy_name=decision.policy_name,
            reason=effective_reason,
            latency_ms=round(latency_ms, 3),
            context=action,
            advisory_action=advisory_action,
            advisory_confidence=advisory_confidence,
            advisory_reason=advisory_reason,
            advisory_classifier=advisory_classifier,
        )

        # 4) Broadcast to live listeners
        self._broadcast({"kind": "decision", **dec_rec})

        return Verdict(
            allowed=allowed,
            action_type=action_type,
            verdict=effective_action,
            matched_rule=decision.matched_rule,
            policy_name=decision.policy_name,
            reason=effective_reason or "",
            latency_ms=round(latency_ms, 3),
            agent_did=agent.did,
            agent_name=agent.name,
            requires_approval=requires_approval,
        )

    # -- trust sync --------------------------------------------------------
    def _sync_trust(self, agent_did: str) -> None:
        """Mirror the RewardEngine score into the store + auto-suspend on collapse."""
        score = self._reward.get_agent_score(agent_did)
        tier = getattr(score, "tier", "standard")
        db.update_agent_trust(agent_did, score.total_score, tier)
        db.add_trust_point(agent_did, score.total_score, tier)
        if score.total_score < _SUSPEND_BELOW:
            db.set_agent_status(agent_did, "suspended")
            self._broadcast(
                {"kind": "agent_suspended", "agent_did": agent_did, "score": score.total_score}
            )

    # -- advisory ----------------------------------------------------------
    def _run_advisory(self, action: dict[str, Any], signals: dict[str, Any] | None):
        """Run the probabilistic advisory classifier. Returns AdvisoryDecision or None."""
        try:
            from app.governance.advisory import trade_advisory

            ctx = {"action": action, "signals": signals or {}}
            return trade_advisory.check(ctx)
        except Exception:
            logger.warning("advisory check failed", exc_info=True)
            return None

    # -- audit integrity ---------------------------------------------------
    def verify_audit(self) -> tuple[bool, str | None]:
        """Verify the in-memory hash chain integrity."""
        return self._audit.verify_integrity()


# Process-wide singleton.
gate = GovernanceGate()
