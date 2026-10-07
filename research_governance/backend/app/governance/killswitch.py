# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Kill switch (AGT hypervisor ``KillSwitch``).

Wraps the real AGT kill switch. Each agent registers a termination callback
that marks it suspended in the store. ``kill()`` records a real ``KillResult``
(with reason) to the runtime event log, so the Governance page shows a genuine
kill history, not just a status flip.

FEATURES.md rows exercised: **Kill Switch**.
"""

from __future__ import annotations

import threading

import app.config  # noqa: F401
from hypervisor.security.kill_switch import KillReason, KillSwitch

from app.store import db

_REASON_MAP = {
    "manual": KillReason.MANUAL,
    "behavioral_drift": KillReason.BEHAVIORAL_DRIFT,
    "rate_limit": KillReason.RATE_LIMIT,
    "ring_breach": KillReason.RING_BREACH,
}


class KillSwitchManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._switch = KillSwitch()
        self._registered: set[str] = set()

    def register(self, agent_did: str) -> None:
        """Register an agent with a callback that suspends it in the store."""
        with self._lock:
            if agent_did in self._registered:
                return

            def _terminate(did: str = agent_did) -> None:
                db.set_agent_status(did, "suspended")

            self._switch.register_agent(agent_did, _terminate)
            self._registered.add(agent_did)

    def kill(self, agent_did: str, agent_name: str = "", reason: str = "manual",
             details: str = "") -> dict:
        """Kill an agent via the AGT kill switch; record the result."""
        self.register(agent_did)  # ensure callback present
        kr = self._switch.kill(
            agent_did=agent_did,
            session_id="govdesk",
            reason=_REASON_MAP.get(reason, KillReason.MANUAL),
            details=details,
        )
        db.add_runtime_event(
            kind="kill" if kr.terminated else "kill_failed",
            agent_did=agent_did,
            agent_name=agent_name,
            detail=f"{reason}: {details}" if details else reason,
            data={"kill_id": kr.kill_id, "terminated": kr.terminated,
                  "reason": kr.reason.value},
        )
        # A killed agent must re-register before it can be killed again.
        with self._lock:
            self._registered.discard(agent_did)
        return {
            "kill_id": kr.kill_id,
            "agent_did": agent_did,
            "terminated": kr.terminated,
            "reason": kr.reason.value,
        }

    def kill_history(self) -> list[dict]:
        return [
            {
                "kill_id": k.kill_id,
                "agent_did": k.agent_did,
                "reason": k.reason.value,
                "terminated": k.terminated,
                "timestamp": k.timestamp.isoformat(),
            }
            for k in self._switch.kill_history
        ]


killswitch = KillSwitchManager()
