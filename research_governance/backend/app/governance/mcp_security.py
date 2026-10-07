# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""MCP tool security — screen data tools before an agent may use them.

Wraps AGT's :class:`agent_os.mcp_security.MCPSecurityScanner`. On startup (and
on demand) we scan every tool in the catalog for poisoning / hidden
instructions / typosquatting, register a cryptographic fingerprint for each,
and persist the verdict. A tool with a CRITICAL finding is **blocked**: the
Market-Data agent is not allowed to use it.

Each use re-runs a rug-pull check so a tool that silently changes its
definition after approval is caught.

FEATURES.md rows exercised: **MCP Security Scanner / Gateway**.
"""

from __future__ import annotations

import threading
import warnings

import app.config  # noqa: F401  (AGT import bootstrap)
from agent_os.mcp_security import MCPSecurityScanner, MCPSeverity

from app.mcp.catalog import CATALOG, MCPToolDef, get_tool
from app.store import db

_SEVERITY_RANK = {None: 0, "info": 1, "warning": 2, "critical": 3}


def _threat_to_dict(t) -> dict:
    return {
        "type": t.threat_type.value,
        "severity": t.severity.value,
        "message": t.message,
        "tool": t.tool_name,
        "server": t.server_name,
    }


class MCPSecurity:
    """Process-wide MCP tool screening state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # The scanner warns when using built-in sample rules; that's expected
        # for a demo. A production deployment would pass an explicit config.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._scanner = MCPSecurityScanner()
        self._scanned = False

    def scan_catalog(self) -> list[dict]:
        """Scan + register every catalog tool; persist and return verdicts."""
        with self._lock:
            results: list[dict] = []
            for tool in CATALOG:
                results.append(self._scan_one(tool))
            self._scanned = True
            return results

    def _scan_one(self, tool: MCPToolDef) -> dict:
        # Register a fingerprint first (enables rug-pull + cross-server checks).
        self._scanner.register_tool(
            tool.name, tool.description, tool.schema, tool.server
        )
        threats = self._scanner.scan_tool(
            tool.name, tool.description, tool.schema, server_name=tool.server
        )
        max_sev = None
        for t in threats:
            if _SEVERITY_RANK[t.severity.value] > _SEVERITY_RANK[max_sev]:
                max_sev = t.severity.value
        # Block the tool if anything critical was found.
        allowed = max_sev != "critical"
        safe = len(threats) == 0
        db.upsert_mcp_scan(
            server=tool.server,
            tool_name=tool.name,
            safe=safe,
            allowed=allowed,
            threat_count=len(threats),
            max_severity=max_sev,
            threats=[_threat_to_dict(t) for t in threats],
            demo_malicious=tool.demo_malicious,
        )
        return {
            "tool": tool.name,
            "server": tool.server,
            "safe": safe,
            "allowed": allowed,
            "threat_count": len(threats),
            "max_severity": max_sev,
        }

    def is_tool_allowed(self, tool_name: str) -> tuple[bool, str]:
        """Return (allowed, reason) for a tool, scanning the catalog if needed."""
        if not self._scanned:
            self.scan_catalog()
        rec = db.get_mcp_scan(tool_name)
        if rec is None:
            return False, f"tool '{tool_name}' is not in the scanned catalog"
        if not rec["allowed"]:
            return False, (
                f"tool '{tool_name}' blocked by MCP security "
                f"({rec['max_severity']}: {rec['threat_count']} threat(s))"
            )
        return True, "tool passed MCP security screening"

    def recheck_rug_pull(self, tool_name: str) -> dict | None:
        """Re-run the rug-pull check for a tool against its current definition."""
        tool = get_tool(tool_name)
        if tool is None:
            return None
        with self._lock:
            threat = self._scanner.check_rug_pull(
                tool.name, tool.description, tool.schema, tool.server
            )
        return _threat_to_dict(threat) if threat else None


# Process-wide singleton.
mcp_security = MCPSecurity()
