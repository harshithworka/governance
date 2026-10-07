# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Shadow AI discovery (AGT ``agent_discovery``).

Finds AI agents "running" across the environment and reconciles them against
the governed registry. Agents that are *not* registered (no DID, unknown owner)
are flagged as **shadow agents** and risk-scored — the ungoverned agents a
security team most needs to find.

For the demo we build a realistic observation set: the 6 governed GovDesk
agents (which reconcile cleanly) plus a few planted shadow agents (a rogue
trading bot, an unregistered MCP server) so discovery has real shadows to
surface. In production the observations would come from the real process /
config / repo scanners (`agent_discovery.scanners.*`).

FEATURES.md rows exercised: **Shadow AI Discovery**.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import app.config  # noqa: F401
from agent_discovery.inventory import AgentInventory
from agent_discovery.models import (
    AgentStatus,
    DetectionBasis,
    DiscoveredAgent,
    Evidence,
    ScanResult,
)
from agent_discovery.reconciler import Reconciler, StaticRegistryProvider
from agent_discovery.risk import RiskScorer

from app.governance.identities import all_agents
from app.store import db


def _observe_governed() -> list[DiscoveredAgent]:
    """Observations for the real governed agents (they carry DIDs → registered)."""
    out: list[DiscoveredAgent] = []
    for a in all_agents():
        merge = {"process": f"govdesk/{a.key}"}
        agent = DiscoveredAgent(
            fingerprint=DiscoveredAgent.compute_fingerprint(merge),
            name=a.name,
            agent_type="govdesk",
            description=a.role,
            did=a.did,
            owner="govdesk@example.com",
            merge_keys=merge,
        )
        agent.add_evidence(Evidence(
            scanner="process-scanner", basis=DetectionBasis.PROCESS,
            source=f"pid://govdesk/{a.key}", detail=f"GovDesk {a.name} process",
            confidence=0.95,
        ))
        out.append(agent)
    return out


def _observe_shadows() -> list[DiscoveredAgent]:
    """Planted shadow observations: ungoverned agents with no DID/owner."""
    specs = [
        ("rogue-trading-bot", "langchain", "Unregistered autonomous trader found in a cron job",
         {"process": "cron/rogue_trader.py"}, None, 0.9, 40),
        ("unknown-mcp-server", "mcp-server", "MCP server exposing tools, not in registry",
         {"endpoint": "localhost:9123"}, None, 0.85, 20),
        ("intern-notebook-agent", "autogen", "AutoGen agent in a shared notebook, no owner",
         {"repo": "data-science/notebooks/agent.ipynb"}, None, 0.6, 10),
    ]
    out: list[DiscoveredAgent] = []
    for name, atype, desc, merge, owner, conf, days_old in specs:
        agent = DiscoveredAgent(
            fingerprint=DiscoveredAgent.compute_fingerprint(merge),
            name=name, agent_type=atype, description=desc,
            did=None, owner=owner, merge_keys=merge,
            first_seen_at=datetime.now(UTC) - timedelta(days=days_old),
        )
        agent.add_evidence(Evidence(
            scanner="process-scanner", basis=DetectionBasis.PROCESS,
            source=str(merge), detail=desc, confidence=conf,
        ))
        out.append(agent)
    return out


class Discovery:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scorer = RiskScorer()

    def scan(self) -> dict:
        """Run a discovery + reconciliation + risk-scoring pass; persist results."""
        with self._lock:
            inventory = AgentInventory()
            observed = _observe_governed() + _observe_shadows()
            inventory.ingest(ScanResult(scanner_name="govdesk-observer", agents=observed,
                                        scanned_targets=len(observed)))

            # Registry = the governed agents (by DID). Reconcile to find shadows.
            registered = [{"did": a.did, "name": a.name} for a in all_agents()]
            provider = StaticRegistryProvider(registered)
            reconciler = Reconciler(inventory, provider)
            # Reconcile is async. We may be called from inside a running event
            # loop (FastAPI startup) where asyncio.run() is illegal, so run the
            # coroutine to completion in a dedicated worker thread that has no
            # running loop of its own.
            with ThreadPoolExecutor(max_workers=1) as ex:
                shadows = ex.submit(lambda: asyncio.run(reconciler.reconcile())).result()

            db.clear_shadow_agents()
            # Persist every observed agent with its reconciled status + risk.
            shadow_fps = {s.agent.fingerprint for s in shadows}
            for agent in inventory.agents:
                is_shadow = agent.fingerprint in shadow_fps
                risk = self._scorer.score(agent)
                recommended = next(
                    (s.recommended_actions for s in shadows if s.agent.fingerprint == agent.fingerprint),
                    [],
                )
                db.upsert_shadow_agent(
                    fingerprint=agent.fingerprint,
                    name=agent.name,
                    agent_type=agent.agent_type,
                    status=agent.status.value if agent.status else AgentStatus.UNKNOWN.value,
                    did=agent.did,
                    owner=agent.owner,
                    confidence=agent.confidence,
                    risk_level=risk.level.value,
                    risk_score=risk.score,
                    factors=risk.factors,
                    recommended=recommended,
                )
            return {
                "total": len(inventory.agents),
                "shadows": len(shadows),
                "registered": len(inventory.agents) - len(shadows),
            }


discovery = Discovery()
