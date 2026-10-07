# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Cryptographic agent identities (AGT ``AgentIdentity``).

Each GovDesk agent gets a real Ed25519 ``did:mesh:...`` identity so every
governed action can be attributed to a specific agent. Identities are created
once per process and registered in the store so the UI can list them.

FEATURES.md rows exercised: **AgentIdentity (DID)**.
"""

from __future__ import annotations

from dataclasses import dataclass

import app.config  # noqa: F401  (ensures AGT is importable)
from agentmesh.identity.agent_id import AgentIdentity

from app.store import db


@dataclass
class GovAgent:
    """A GovDesk agent: its AGT identity plus role/ring metadata."""

    key: str                 # short internal key, e.g. "research"
    name: str                # display name
    role: str                # role label
    ring: str                # execution ring label (enforced for real in Phase 3)
    capabilities: list[str]
    policy_file: str         # policy YAML filename under app/policies/
    identity: AgentIdentity

    @property
    def did(self) -> str:
        return str(self.identity.did)


# The six-agent desk (Phase 1 wires the first four into the graph; the
# governance/discovery agent is monitor-only and used by later phases).
_AGENT_SPECS = [
    ("research", "Research Agent", "research", "restricted-net",
     ["web_search", "read_market_data"], "research.yaml"),
    ("market_data", "Market-Data Agent", "market_data", "restricted-net",
     ["read_market_data", "read_alphavantage"], "market_data.yaml"),
    ("strategy", "Strategy Agent", "strategy", "no-net",
     ["read_market_data", "read_research", "draft_proposal"], "strategy.yaml"),
    ("risk", "Risk Officer", "risk", "no-net",
     ["assess_trade"], "risk.yaml"),
    ("execution", "Execution Agent", "execution", "tightest",
     ["place_trade"], "execution.yaml"),
    ("governance", "Governance / Discovery", "governance", "monitor",
     ["scan", "aggregate", "kill"], "research.yaml"),
]


_AGENTS: dict[str, GovAgent] = {}


def build_agents() -> dict[str, GovAgent]:
    """Create (once) and register all agent identities. Returns key -> GovAgent."""
    if _AGENTS:
        return _AGENTS

    for key, name, role, ring, caps, policy_file in _AGENT_SPECS:
        identity = AgentIdentity.create(
            name, sponsor="govdesk@example.com", capabilities=caps
        )
        agent = GovAgent(
            key=key, name=name, role=role, ring=ring,
            capabilities=caps, policy_file=policy_file, identity=identity,
        )
        _AGENTS[key] = agent
        db.upsert_agent(
            did=agent.did, name=name, role=role, ring=ring,
            capabilities=caps, trust_score=500, trust_tier="standard",
        )
    return _AGENTS


def get_agent(key: str) -> GovAgent:
    if not _AGENTS:
        build_agents()
    return _AGENTS[key]


def all_agents() -> list[GovAgent]:
    if not _AGENTS:
        build_agents()
    return list(_AGENTS.values())
