# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""GovDesk configuration and AGT import bootstrap.

Importing this module has one critical side effect: it ensures the Agent
Governance Toolkit packages are importable. The published wheel ships only a
partial engine, so we prefer this repository's local source tree
(``agent-governance-python/*/src``) by putting it on ``sys.path`` — the same
approach validated when standing up the demos.

All runtime configuration is read from environment variables (optionally via a
local ``.env`` file). Phase 1 requires none of them.
"""

from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

# Silence the (harmless) deprecation warnings emitted by the agentmesh/agent_os
# import shims — the code they point to is what we intentionally run.
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------------------
# Locate the repo root and add the local AGT source trees to sys.path.
# research_governance/backend/app/config.py  ->  repo root is parents[3].
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
REPO_ROOT = _THIS.parents[3]
_PY_ROOT = REPO_ROOT / "agent-governance-python"

_AGT_SRC_DIRS = [
    _PY_ROOT / "agent-mesh" / "src",
    _PY_ROOT / "agent-os" / "src",
    _PY_ROOT / "agent-compliance" / "src",
    _PY_ROOT / "agent-hypervisor" / "src",
    _PY_ROOT / "agent-sre" / "src",
    _PY_ROOT / "agent-discovery" / "src",
    _PY_ROOT / "agent-marketplace" / "src",
]


def _ensure_agt_on_path() -> list[str]:
    """Prepend local AGT source dirs to sys.path if present. Returns those used."""
    used: list[str] = []
    for d in _AGT_SRC_DIRS:
        if d.is_dir():
            s = str(d)
            if s not in sys.path:
                sys.path.insert(0, s)
            used.append(s)
    return used


AGT_SOURCE_DIRS = _ensure_agt_on_path()


# ---------------------------------------------------------------------------
# Load .env (optional) and expose settings.
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)


_load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from environment variables."""

    # LLM / research / data (all optional in Phase 1)
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    groq_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    )
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))

    # JEV — per-agent output safety judge (OpenRouter, OpenAI-compatible).
    jev_api_key: str = field(default_factory=lambda: os.getenv("JEV_API_KEY", ""))
    # Jev is a TypeSafe "System One" decision model on OpenRouter, called via the
    # Decisions API (not chat completions). ~typesafe/jev-latest tracks newest.
    jev_model: str = field(
        default_factory=lambda: os.getenv("JEV_MODEL", "typesafe/jev-1.13")
    )
    # Groq is the JEV fallback when JEV_API_KEY (OpenRouter) is unset. It uses a
    # SECOND Groq key (env GROQ_MODEL_2 — a dedicated key, kept separate from the
    # Strategy agent's GROQ_API_KEY so JEV has its own quota) and a small, fast
    # judge model. Scored via Groq's OpenAI-compatible REST endpoint.
    groq_jev_api_key: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL_2", "")
    )
    groq_jev_model: str = field(
        default_factory=lambda: os.getenv("GROQ_JEV_MODEL", "openai/gpt-oss-20b")
    )

    finnhub_api_key: str = field(default_factory=lambda: os.getenv("FINNHUB_API_KEY", ""))
    alphavantage_api_key: str = field(
        default_factory=lambda: os.getenv("ALPHAVANTAGE_API_KEY", "")
    )

    # Audit signing (optional)
    audit_secret_key_hex: str = field(
        default_factory=lambda: os.getenv("AGT_AUDIT_SECRET_KEY", "")
    )

    # Store
    db_path: str = field(default_factory=lambda: os.getenv("GOVDESK_DB", "govdesk.db"))

    # Server
    host: str = field(default_factory=lambda: os.getenv("GOVDESK_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("GOVDESK_PORT", "8099")))
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "GOVDESK_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            )
        )
    )

    # Capability flags (what's live based on which keys are present)
    @property
    def has_llm(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key)

    @property
    def has_research(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def has_jev(self) -> bool:
        return bool(self.jev_api_key)

    @property
    def has_market_data(self) -> bool:
        return bool(self.finnhub_api_key or self.alphavantage_api_key)

    @property
    def audit_secret_key(self) -> bytes | None:
        """Decode the hex audit key if provided and valid (>=32 bytes)."""
        if not self.audit_secret_key_hex:
            return None
        try:
            raw = bytes.fromhex(self.audit_secret_key_hex)
        except ValueError:
            return None
        return raw if len(raw) >= 32 else None


settings = Settings()


def resolve_db_path() -> str:
    """Return an absolute path for the SQLite DB, rooted at the backend dir."""
    p = Path(settings.db_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[1] / p
    return str(p)
