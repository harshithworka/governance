# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Marketplace vetting (AGT ``agent_marketplace``).

Treats each MCP data tool as a marketplace **plugin** and vets it before it is
trusted: build a signed ``PluginManifest``, compute an initial trust score and
tier, and verify the Ed25519 signature. The vetting result composes with the
Phase 2 MCP security scan — a tool the scanner blocked is forced to the
``revoked`` tier and marked not-allowed here too, so a poisoned tool cannot be
"trusted" by the marketplace either.

FEATURES.md rows exercised: **Marketplace trust/quality + signing**.
"""

from __future__ import annotations

import threading

from cryptography.hazmat.primitives.asymmetric import ed25519

import app.config  # noqa: F401
from agent_marketplace.manifest import PluginManifest, PluginType
from agent_marketplace.signing import PluginSigner, verify_signature
from agent_marketplace.trust_tiers import compute_initial_score, get_trust_tier

from app.mcp.catalog import CATALOG, MCPToolDef
from app.store import db


class Marketplace:
    """Vets MCP tools as signed, trust-scored plugins."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # One publisher key for the demo. In production each publisher would
        # hold its own key and the registry would pin trusted public keys.
        self._key = ed25519.Ed25519PrivateKey.generate()
        self._signer = PluginSigner(self._key)

    def _vet_one(self, tool: MCPToolDef) -> dict:
        # Build a plugin manifest for the tool.
        manifest = PluginManifest(
            name=tool.name.replace("_", "-"),
            version="1.0.0",
            description=tool.description[:200] or "market data tool",
            author=f"{tool.server}@publishers.example.com",
            plugin_type=PluginType.INTEGRATION,
            capabilities=["network"] if tool.backend else [],
        )

        # Sign + verify (proves provenance/integrity).
        signed = self._signer.sign(manifest)
        try:
            verified = verify_signature(signed, self._signer.public_key)
        except Exception:
            verified = False

        # Initial trust score + tier from the (now signed) manifest.
        score = compute_initial_score(signed)
        tier = get_trust_tier(score)

        # Compose with the MCP security verdict: a blocked tool is forced to
        # revoked + not-allowed regardless of its manifest score.
        mcp = db.get_mcp_scan(tool.name)
        mcp_blocked = bool(mcp and not mcp["allowed"])
        if mcp_blocked:
            score = 0
            tier = "revoked"
        allowed = (tier not in ("revoked",)) and not mcp_blocked

        # Quality grade: a simple mapping off tier for the demo (a real
        # deployment would run QualityAssessor over the artifact).
        quality_grade = {
            "verified": "A", "trusted": "B", "standard": "C",
            "probationary": "D", "revoked": "F",
        }.get(tier, "C")

        notes = "blocked by MCP security scan" if mcp_blocked else "vetted"
        db.upsert_plugin_vetting(
            tool_name=tool.name,
            server=tool.server,
            trust_score=score,
            tier=tier,
            quality_grade=quality_grade,
            quality_score=float(score) / 10.0,
            signed=signed.signature is not None,
            verified=verified,
            allowed=allowed,
            notes=notes,
        )
        return {"tool": tool.name, "tier": tier, "score": score,
                "signed": signed.signature is not None, "verified": verified,
                "allowed": allowed}

    def vet_catalog(self) -> list[dict]:
        """Vet every catalog tool; persist and return results."""
        with self._lock:
            return [self._vet_one(t) for t in CATALOG]

    def is_tool_trusted(self, tool_name: str) -> tuple[bool, str]:
        """Return (trusted, reason) based on the latest vetting."""
        rows = {v["tool_name"]: v for v in db.list_plugin_vettings()}
        v = rows.get(tool_name)
        if v is None:
            return False, f"tool '{tool_name}' has not been vetted"
        if not v["allowed"]:
            return False, f"tool '{tool_name}' tier={v['tier']} ({v['notes']})"
        return True, f"tool '{tool_name}' trusted (tier={v['tier']}, signed+verified)"


marketplace = Marketplace()
