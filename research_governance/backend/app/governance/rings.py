# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Execution rings + command denylist (AGT hypervisor).

Each agent is pinned to an :class:`ExecutionRing` that defines its blast radius
(network / filesystem / subprocess). Before a node uses a resource, it asks the
ring enforcer whether its ring permits it; a denial is structural, not advisory.
The command denylist blocks dangerous shell commands outright.

Ring assignment (tightest wins):
  - execution  -> RING_3_SANDBOX   (no network, no subprocess — can only decide trades)
  - risk       -> RING_3_SANDBOX   (pure deterministic assessment)
  - strategy   -> RING_3_SANDBOX   (no network; works off provided research/data)
  - research   -> RING_2_STANDARD  (network for Tavily)
  - market_data-> RING_2_STANDARD  (network for Finnhub)
  - governance -> RING_2_STANDARD  (monitor)

FEATURES.md rows exercised: **Execution Rings**, **Command denylist**.
"""

from __future__ import annotations

import threading

import app.config  # noqa: F401
from hypervisor.models import ExecutionRing
from hypervisor.rings.enforcer import ResourceType, RingEnforcer

from app.store import db

# Agent key -> ring. Lower ring number = more privileged.
_AGENT_RINGS: dict[str, ExecutionRing] = {
    "research": ExecutionRing.RING_2_STANDARD,
    "market_data": ExecutionRing.RING_2_STANDARD,
    "governance": ExecutionRing.RING_2_STANDARD,
    "strategy": ExecutionRing.RING_3_SANDBOX,
    "risk": ExecutionRing.RING_3_SANDBOX,
    "execution": ExecutionRing.RING_3_SANDBOX,
}

_RING_LABELS = {
    ExecutionRing.RING_0_ROOT: "ring-0-root",
    ExecutionRing.RING_1_PRIVILEGED: "ring-1-privileged",
    ExecutionRing.RING_2_STANDARD: "ring-2-standard",
    ExecutionRing.RING_3_SANDBOX: "ring-3-sandbox",
}

_RESOURCE_BY_NAME = {
    "network": ResourceType.NETWORK,
    "filesystem": ResourceType.FILESYSTEM,
    "subprocess": ResourceType.SUBPROCESS,
    "tool_execution": ResourceType.TOOL_EXECUTION,
}


class Rings:
    """Process-wide ring enforcement."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._enforcer = RingEnforcer()

    def ring_of(self, agent_key: str) -> ExecutionRing:
        return _AGENT_RINGS.get(agent_key, ExecutionRing.RING_3_SANDBOX)

    def ring_label(self, agent_key: str) -> str:
        return _RING_LABELS[self.ring_of(agent_key)]

    def check_resource(
        self, agent_key: str, resource: str, *, agent_did: str = "", agent_name: str = ""
    ) -> tuple[bool, str]:
        """Return (allowed, reason) for an agent using a resource type."""
        rtype = _RESOURCE_BY_NAME.get(resource)
        if rtype is None:
            return False, f"unknown resource type '{resource}'"
        ring = self.ring_of(agent_key)
        result = self._enforcer.check_resource(ring, rtype)
        if not result.allowed:
            db.add_runtime_event(
                kind="ring_denied",
                agent_did=agent_did,
                agent_name=agent_name,
                detail=result.reason,
                data={"resource": resource, "ring": _RING_LABELS[ring]},
            )
        return result.allowed, result.reason

    def check_command(
        self, command: str, *, agent_did: str = "", agent_name: str = ""
    ) -> tuple[bool, str]:
        """Return (allowed, reason) for a shell command against the denylist."""
        result = self._enforcer.check_command(command)
        if not result.allowed:
            db.add_runtime_event(
                kind="command_denied",
                agent_did=agent_did,
                agent_name=agent_name,
                detail=result.reason,
                data={"command": result.command,
                      "matched": result.matched_denylist_entry},
            )
        return result.allowed, result.reason

    def ring_table(self) -> list[dict]:
        """Ring assignment + constraints per agent (for the UI)."""
        out = []
        for key, ring in _AGENT_RINGS.items():
            c = self._enforcer.get_constraints(ring)
            out.append({
                "agent_key": key,
                "ring": _RING_LABELS[ring],
                "ring_level": int(ring.value),
                "network": c.network_allowed,
                "filesystem": c.filesystem_scope,
                "subprocess": c.subprocess_allowed,
                "max_concurrent_tools": c.max_concurrent_tools,
            })
        return out


rings = Rings()
