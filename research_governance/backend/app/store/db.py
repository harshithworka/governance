# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""SQLite-backed store for GovDesk.

A thin, thread-safe persistence layer. Table shapes mirror the AGT Engine API
contract models (``agentmesh.engine_api.models``) so the data a frontend reads
is already contract-aligned: agents, decisions, audit entries, trust scores,
and the human-approval queue.

stdlib ``sqlite3`` only — no ORM dependency. One module-level connection guarded
by a lock; SQLite WAL mode is enabled for concurrent reads during writes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from app.config import resolve_db_path

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def get_conn() -> sqlite3.Connection:
    """Return the shared SQLite connection, creating it on first use."""
    global _CONN
    with _LOCK:
        if _CONN is None:
            conn = sqlite3.connect(
                resolve_db_path(), check_same_thread=False, isolation_level=None
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            _CONN = conn
        return _CONN


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    did            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    role           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',   -- active|suspended|revoked
    ring           TEXT,
    capabilities   TEXT NOT NULL DEFAULT '[]',        -- JSON array
    trust_score    INTEGER NOT NULL DEFAULT 500,
    trust_tier     TEXT NOT NULL DEFAULT 'standard',
    last_active    REAL,
    created_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id    TEXT PRIMARY KEY,
    run_id         TEXT,
    timestamp      REAL NOT NULL,
    agent_did      TEXT NOT NULL,
    agent_name     TEXT,
    action         TEXT NOT NULL,
    resource       TEXT,
    verdict        TEXT NOT NULL,                      -- allow|deny|warn|require_approval
    matched_rule   TEXT,
    policy_name    TEXT,
    reason         TEXT,
    latency_ms     REAL,
    context_json   TEXT,
    advisory_action     TEXT,              -- allow|flag_for_review|block (if run)
    advisory_confidence REAL,
    advisory_reason     TEXT,
    advisory_classifier TEXT
);

CREATE TABLE IF NOT EXISTS audit_entries (
    entry_id       TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    agent_did      TEXT NOT NULL,
    action         TEXT NOT NULL,
    outcome        TEXT NOT NULL,                      -- success|failure|denied
    resource       TEXT,
    policy_decision TEXT,
    entry_hash     TEXT,
    previous_hash  TEXT,
    data_json      TEXT
);

CREATE TABLE IF NOT EXISTS trust_scores (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_did      TEXT NOT NULL,
    timestamp      REAL NOT NULL,
    trust_score    INTEGER NOT NULL,
    trust_tier     TEXT,
    dimensions_json TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id    TEXT PRIMARY KEY,
    run_id         TEXT,
    created_at     REAL NOT NULL,
    agent_did      TEXT NOT NULL,
    action         TEXT NOT NULL,
    reason         TEXT,
    payload_json   TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',    -- pending|approved|rejected
    resolved_at    REAL,
    resolver       TEXT
);

CREATE TABLE IF NOT EXISTS mcp_scans (
    scan_id        TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    server         TEXT NOT NULL,
    tool_name      TEXT NOT NULL,
    safe           INTEGER NOT NULL,                  -- 1 safe, 0 flagged
    allowed        INTEGER NOT NULL DEFAULT 1,        -- may the agent use it?
    threat_count   INTEGER NOT NULL DEFAULT 0,
    max_severity   TEXT,                              -- info|warning|critical
    threats_json   TEXT,
    demo_malicious INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_decisions_agent ON decisions(agent_did);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_entries(agent_did);
CREATE INDEX IF NOT EXISTS idx_trust_agent ON trust_scores(agent_did);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_mcp_scans_tool ON mcp_scans(tool_name);

CREATE TABLE IF NOT EXISTS runtime_events (
    event_id       TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    agent_did      TEXT,
    agent_name     TEXT,
    kind           TEXT NOT NULL,     -- ring_denied|command_denied|breaker_open|breaker_reset|kill|kill_failed
    detail         TEXT,
    data_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_runtime_kind ON runtime_events(kind);

CREATE TABLE IF NOT EXISTS shadow_agents (
    fingerprint    TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    name           TEXT NOT NULL,
    agent_type     TEXT,
    status         TEXT NOT NULL,     -- registered|shadow|unregistered
    did            TEXT,
    owner          TEXT,
    confidence     REAL,
    risk_level     TEXT,
    risk_score     REAL,
    factors_json   TEXT,
    recommended_json TEXT
);

CREATE TABLE IF NOT EXISTS plugin_vettings (
    tool_name      TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    server         TEXT,
    trust_score    INTEGER,
    tier           TEXT,
    quality_grade  TEXT,
    quality_score  REAL,
    signed         INTEGER NOT NULL DEFAULT 0,
    verified       INTEGER NOT NULL DEFAULT 0,
    allowed        INTEGER NOT NULL DEFAULT 1,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS intake_events (
    intake_id      TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    ok             INTEGER NOT NULL,
    original_len   INTEGER,
    clean_query    TEXT,
    redactions_json TEXT,
    injection_detected INTEGER NOT NULL DEFAULT 0,
    injection_threat TEXT,
    injection_reason TEXT,
    injection_patterns_json TEXT,
    company        TEXT,
    symbol         TEXT,
    block_reason   TEXT
);

CREATE TABLE IF NOT EXISTS rag_retrievals (
    retrieval_id   TEXT PRIMARY KEY,
    timestamp      REAL NOT NULL,
    run_id         TEXT,
    symbol         TEXT,
    source         TEXT,
    report_url     TEXT,
    chunks_total   INTEGER,
    chunks_used    INTEGER,
    chunks_flagged INTEGER,
    available      INTEGER NOT NULL DEFAULT 0,
    reason         TEXT
);
"""


def init_db() -> None:
    """Create tables if they do not exist."""
    with _LOCK:
        get_conn().executescript(_SCHEMA)


def reset_db() -> None:
    """Drop all rows (used by tests / fresh demo runs)."""
    with _LOCK:
        conn = get_conn()
        for t in ("agents", "decisions", "audit_entries", "trust_scores",
                  "approvals", "mcp_scans", "runtime_events",
                  "shadow_agents", "plugin_vettings",
                  "intake_events", "rag_retrievals"):
            conn.execute(f"DELETE FROM {t};")


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
def upsert_agent(
    did: str,
    name: str,
    role: str,
    *,
    ring: str | None = None,
    capabilities: list[str] | None = None,
    status: str = "active",
    trust_score: int = 500,
    trust_tier: str = "standard",
) -> None:
    with _LOCK:
        get_conn().execute(
            """
            INSERT INTO agents (did, name, role, status, ring, capabilities,
                                trust_score, trust_tier, last_active, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(did) DO UPDATE SET
                name=excluded.name, role=excluded.role, ring=excluded.ring,
                capabilities=excluded.capabilities
            """,
            (
                did, name, role, status, ring,
                json.dumps(capabilities or []), trust_score, trust_tier,
                _now(), _now(),
            ),
        )


def set_agent_status(did: str, status: str) -> None:
    with _LOCK:
        get_conn().execute("UPDATE agents SET status=? WHERE did=?", (status, did))


def update_agent_trust(did: str, score: int, tier: str) -> None:
    with _LOCK:
        get_conn().execute(
            "UPDATE agents SET trust_score=?, trust_tier=?, last_active=? WHERE did=?",
            (score, tier, _now(), did),
        )


def list_agents() -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute("SELECT * FROM agents ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["capabilities"] = json.loads(d.get("capabilities") or "[]")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
def add_decision(
    *,
    agent_did: str,
    agent_name: str,
    action: str,
    verdict: str,
    run_id: str | None = None,
    resource: str | None = None,
    matched_rule: str | None = None,
    policy_name: str | None = None,
    reason: str | None = None,
    latency_ms: float | None = None,
    context: dict | None = None,
    advisory_action: str | None = None,
    advisory_confidence: float | None = None,
    advisory_reason: str | None = None,
    advisory_classifier: str | None = None,
) -> dict[str, Any]:
    rec = {
        "decision_id": _new_id("dec"),
        "run_id": run_id,
        "timestamp": _now(),
        "agent_did": agent_did,
        "agent_name": agent_name,
        "action": action,
        "resource": resource,
        "verdict": verdict,
        "matched_rule": matched_rule,
        "policy_name": policy_name,
        "reason": reason,
        "latency_ms": latency_ms,
        "context_json": json.dumps(context or {}),
        "advisory_action": advisory_action,
        "advisory_confidence": advisory_confidence,
        "advisory_reason": advisory_reason,
        "advisory_classifier": advisory_classifier,
    }
    with _LOCK:
        get_conn().execute(
            """INSERT INTO decisions
               (decision_id, run_id, timestamp, agent_did, agent_name, action,
                resource, verdict, matched_rule, policy_name, reason, latency_ms,
                context_json, advisory_action, advisory_confidence, advisory_reason,
                advisory_classifier)
               VALUES (:decision_id,:run_id,:timestamp,:agent_did,:agent_name,:action,
                       :resource,:verdict,:matched_rule,:policy_name,:reason,:latency_ms,
                       :context_json,:advisory_action,:advisory_confidence,:advisory_reason,
                       :advisory_classifier)""",
            rec,
        )
    return rec


def list_advisory(limit: int = 100) -> list[dict[str, Any]]:
    """Decisions where the advisory layer flagged or blocked a trade."""
    with _LOCK:
        rows = get_conn().execute(
            """SELECT * FROM decisions
               WHERE advisory_action IS NOT NULL AND advisory_action != 'allow'
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_decisions(limit: int = 100, agent_did: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        if agent_did:
            rows = get_conn().execute(
                "SELECT * FROM decisions WHERE agent_did=? ORDER BY timestamp DESC LIMIT ?",
                (agent_did, limit),
            ).fetchall()
        else:
            rows = get_conn().execute(
                "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Audit entries
# ---------------------------------------------------------------------------
def add_audit_entry(
    *,
    entry_id: str,
    agent_did: str,
    action: str,
    outcome: str,
    resource: str | None = None,
    policy_decision: str | None = None,
    entry_hash: str | None = None,
    previous_hash: str | None = None,
    data: dict | None = None,
) -> None:
    with _LOCK:
        get_conn().execute(
            """INSERT OR REPLACE INTO audit_entries
               (entry_id, timestamp, agent_did, action, outcome, resource,
                policy_decision, entry_hash, previous_hash, data_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                entry_id, _now(), agent_did, action, outcome, resource,
                policy_decision, entry_hash, previous_hash, json.dumps(data or {}),
            ),
        )


def list_audit(limit: int = 200, agent_did: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        if agent_did:
            rows = get_conn().execute(
                "SELECT * FROM audit_entries WHERE agent_did=? ORDER BY timestamp DESC LIMIT ?",
                (agent_did, limit),
            ).fetchall()
        else:
            rows = get_conn().execute(
                "SELECT * FROM audit_entries ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Trust history
# ---------------------------------------------------------------------------
def add_trust_point(
    agent_did: str, score: int, tier: str | None = None, dimensions: dict | None = None
) -> None:
    with _LOCK:
        get_conn().execute(
            """INSERT INTO trust_scores (agent_did, timestamp, trust_score, trust_tier, dimensions_json)
               VALUES (?,?,?,?,?)""",
            (agent_did, _now(), score, tier, json.dumps(dimensions or {})),
        )


def trust_history(agent_did: str, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM trust_scores WHERE agent_did=? ORDER BY timestamp DESC LIMIT ?",
            (agent_did, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["dimensions"] = json.loads(d.pop("dimensions_json") or "{}")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Approvals queue
# ---------------------------------------------------------------------------
def add_approval(
    *, agent_did: str, action: str, reason: str, payload: dict, run_id: str | None = None
) -> dict[str, Any]:
    rec = {
        "approval_id": _new_id("appr"),
        "run_id": run_id,
        "created_at": _now(),
        "agent_did": agent_did,
        "action": action,
        "reason": reason,
        "payload_json": json.dumps(payload),
        "status": "pending",
        "resolved_at": None,
        "resolver": None,
    }
    with _LOCK:
        get_conn().execute(
            """INSERT INTO approvals
               (approval_id, run_id, created_at, agent_did, action, reason,
                payload_json, status, resolved_at, resolver)
               VALUES (:approval_id,:run_id,:created_at,:agent_did,:action,:reason,
                       :payload_json,:status,:resolved_at,:resolver)""",
            rec,
        )
    return rec


def resolve_approval(approval_id: str, approved: bool, resolver: str = "human") -> dict | None:
    with _LOCK:
        conn = get_conn()
        conn.execute(
            "UPDATE approvals SET status=?, resolved_at=?, resolver=? WHERE approval_id=? AND status='pending'",
            ("approved" if approved else "rejected", _now(), resolver, approval_id),
        )
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
    return dict(row) if row else None


def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        if status:
            rows = get_conn().execute(
                "SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = get_conn().execute(
                "SELECT * FROM approvals ORDER BY created_at DESC"
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json") or "{}")
        out.append(d)
    return out


def get_approval(approval_id: str) -> dict | None:
    with _LOCK:
        row = get_conn().execute(
            "SELECT * FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    return d


# ---------------------------------------------------------------------------
# MCP tool scans
# ---------------------------------------------------------------------------
def upsert_mcp_scan(
    *,
    server: str,
    tool_name: str,
    safe: bool,
    allowed: bool,
    threat_count: int,
    max_severity: str | None,
    threats: list[dict] | None = None,
    demo_malicious: bool = False,
) -> dict[str, Any]:
    """Record (replace) the latest scan verdict for a tool."""
    rec = {
        "scan_id": f"scan_{server}::{tool_name}",
        "timestamp": _now(),
        "server": server,
        "tool_name": tool_name,
        "safe": 1 if safe else 0,
        "allowed": 1 if allowed else 0,
        "threat_count": threat_count,
        "max_severity": max_severity,
        "threats_json": json.dumps(threats or []),
        "demo_malicious": 1 if demo_malicious else 0,
    }
    with _LOCK:
        get_conn().execute(
            """INSERT OR REPLACE INTO mcp_scans
               (scan_id, timestamp, server, tool_name, safe, allowed, threat_count,
                max_severity, threats_json, demo_malicious)
               VALUES (:scan_id,:timestamp,:server,:tool_name,:safe,:allowed,:threat_count,
                       :max_severity,:threats_json,:demo_malicious)""",
            rec,
        )
    return rec


def delete_mcp_scan(tool_name: str) -> None:
    """Remove the stored scan verdict for a tool (used when a demo-injected
    tool is removed from the catalog so its stale verdict row doesn't linger)."""
    with _LOCK:
        get_conn().execute("DELETE FROM mcp_scans WHERE tool_name = ?;", (tool_name,))


def list_mcp_scans() -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM mcp_scans ORDER BY demo_malicious DESC, tool_name"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["safe"] = bool(d["safe"])
        d["allowed"] = bool(d["allowed"])
        d["demo_malicious"] = bool(d["demo_malicious"])
        d["threats"] = json.loads(d.pop("threats_json") or "[]")
        out.append(d)
    return out


def get_mcp_scan(tool_name: str) -> dict[str, Any] | None:
    with _LOCK:
        row = get_conn().execute(
            "SELECT * FROM mcp_scans WHERE tool_name=? ORDER BY timestamp DESC LIMIT 1",
            (tool_name,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["safe"] = bool(d["safe"])
    d["allowed"] = bool(d["allowed"])
    d["demo_malicious"] = bool(d["demo_malicious"])
    d["threats"] = json.loads(d.pop("threats_json") or "[]")
    return d


# ---------------------------------------------------------------------------
# Runtime events (ring denials, command denials, breaker trips, kills)
# ---------------------------------------------------------------------------
def add_runtime_event(
    *,
    kind: str,
    agent_did: str | None = None,
    agent_name: str | None = None,
    detail: str | None = None,
    data: dict | None = None,
) -> dict[str, Any]:
    rec = {
        "event_id": _new_id("evt"),
        "timestamp": _now(),
        "agent_did": agent_did,
        "agent_name": agent_name,
        "kind": kind,
        "detail": detail,
        "data_json": json.dumps(data or {}),
    }
    with _LOCK:
        get_conn().execute(
            """INSERT INTO runtime_events
               (event_id, timestamp, agent_did, agent_name, kind, detail, data_json)
               VALUES (:event_id,:timestamp,:agent_did,:agent_name,:kind,:detail,:data_json)""",
            rec,
        )
    return rec


def list_runtime_events(limit: int = 200, kind: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        if kind:
            rows = get_conn().execute(
                "SELECT * FROM runtime_events WHERE kind=? ORDER BY timestamp DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = get_conn().execute(
                "SELECT * FROM runtime_events ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d.pop("data_json") or "{}")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Shadow discovery
# ---------------------------------------------------------------------------
def upsert_shadow_agent(
    *,
    fingerprint: str,
    name: str,
    agent_type: str,
    status: str,
    did: str | None = None,
    owner: str | None = None,
    confidence: float = 0.0,
    risk_level: str | None = None,
    risk_score: float | None = None,
    factors: list[str] | None = None,
    recommended: list[str] | None = None,
) -> None:
    with _LOCK:
        get_conn().execute(
            """INSERT OR REPLACE INTO shadow_agents
               (fingerprint, timestamp, name, agent_type, status, did, owner,
                confidence, risk_level, risk_score, factors_json, recommended_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fingerprint, _now(), name, agent_type, status, did, owner,
                confidence, risk_level, risk_score,
                json.dumps(factors or []), json.dumps(recommended or []),
            ),
        )


def clear_shadow_agents() -> None:
    with _LOCK:
        get_conn().execute("DELETE FROM shadow_agents;")


def list_shadow_agents() -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM shadow_agents ORDER BY risk_score DESC"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["factors"] = json.loads(d.pop("factors_json") or "[]")
        d["recommended"] = json.loads(d.pop("recommended_json") or "[]")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Marketplace plugin vetting
# ---------------------------------------------------------------------------
def upsert_plugin_vetting(
    *,
    tool_name: str,
    server: str,
    trust_score: int,
    tier: str,
    quality_grade: str | None,
    quality_score: float | None,
    signed: bool,
    verified: bool,
    allowed: bool,
    notes: str | None = None,
) -> None:
    with _LOCK:
        get_conn().execute(
            """INSERT OR REPLACE INTO plugin_vettings
               (tool_name, timestamp, server, trust_score, tier, quality_grade,
                quality_score, signed, verified, allowed, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tool_name, _now(), server, trust_score, tier, quality_grade,
                quality_score, 1 if signed else 0, 1 if verified else 0,
                1 if allowed else 0, notes,
            ),
        )


def delete_plugin_vetting(tool_name: str) -> None:
    """Remove the stored vetting for a tool (used when a demo-injected tool is
    removed from the catalog so its stale vetting row doesn't linger)."""
    with _LOCK:
        get_conn().execute("DELETE FROM plugin_vettings WHERE tool_name = ?;", (tool_name,))


def list_plugin_vettings() -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM plugin_vettings ORDER BY trust_score DESC"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["signed"] = bool(d["signed"])
        d["verified"] = bool(d["verified"])
        d["allowed"] = bool(d["allowed"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Intake events (governed prompt entry)
# ---------------------------------------------------------------------------
def add_intake_event(result: dict) -> dict[str, Any]:
    rec = {
        "intake_id": _new_id("intake"),
        "timestamp": _now(),
        "ok": 1 if result.get("ok") else 0,
        "original_len": result.get("original_len"),
        "clean_query": result.get("clean_query"),
        "redactions_json": json.dumps(result.get("redactions") or []),
        "injection_detected": 1 if result.get("injection_detected") else 0,
        "injection_threat": result.get("injection_threat"),
        "injection_reason": result.get("injection_reason"),
        "injection_patterns_json": json.dumps(result.get("injection_patterns") or []),
        "company": result.get("company"),
        "symbol": result.get("symbol"),
        "block_reason": result.get("block_reason"),
    }
    with _LOCK:
        get_conn().execute(
            """INSERT INTO intake_events
               (intake_id, timestamp, ok, original_len, clean_query, redactions_json,
                injection_detected, injection_threat, injection_reason,
                injection_patterns_json, company, symbol, block_reason)
               VALUES (:intake_id,:timestamp,:ok,:original_len,:clean_query,:redactions_json,
                       :injection_detected,:injection_threat,:injection_reason,
                       :injection_patterns_json,:company,:symbol,:block_reason)""",
            rec,
        )
    return rec


def list_intake_events(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM intake_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["ok"] = bool(d["ok"])
        d["injection_detected"] = bool(d["injection_detected"])
        d["redactions"] = json.loads(d.pop("redactions_json") or "[]")
        d["injection_patterns"] = json.loads(d.pop("injection_patterns_json") or "[]")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# RAG retrievals
# ---------------------------------------------------------------------------
def add_rag_retrieval(
    *,
    run_id: str | None,
    symbol: str,
    source: str,
    report_url: str | None,
    chunks_total: int,
    chunks_used: int,
    chunks_flagged: int,
    available: bool,
    reason: str,
) -> None:
    with _LOCK:
        get_conn().execute(
            """INSERT INTO rag_retrievals
               (retrieval_id, timestamp, run_id, symbol, source, report_url,
                chunks_total, chunks_used, chunks_flagged, available, reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _new_id("rag"), _now(), run_id, symbol, source, report_url,
                chunks_total, chunks_used, chunks_flagged,
                1 if available else 0, reason,
            ),
        )


def list_rag_retrievals(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM rag_retrievals ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["available"] = bool(d["available"])
        out.append(d)
    return out
