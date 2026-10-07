# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Governed intake — the first gate a user query passes through.

A user submits a free-text query ("Do a full analysis of HDFC Bank. My phone is
9876543210"). Before anything else runs, this module:

1. **Redacts PII/credentials** from the query (AGT ``CredentialRedactor`` for
   secrets, plus our own masking of the PII spans it finds, plus an Indian PAN
   pattern it doesn't ship). The redacted text is what gets logged, displayed,
   and passed downstream — the raw query with PII never leaves intake.
2. **Scans for prompt injection** (AGT ``PromptInjectionDetector``). If the
   query is a detected injection at MEDIUM+ threat, the run is **blocked** and
   the reason (matched patterns + explanation) is returned. This is the
   "block and show why" gate.
3. **Resolves the company to an NSE symbol** using the LLM to extract the
   company name, then the NSE equity master to map it to a ticker.

FEATURES.md rows exercised: **Credential redactor**, **Prompt injection detector**.
"""

from __future__ import annotations

import re
import threading
import warnings
from dataclasses import dataclass, field
from typing import Any

import app.config  # noqa: F401
from agent_compliance.prompt_defense import PromptDefenseEvaluator
from agent_os.credential_redactor import CredentialRedactor
from agent_os.prompt_injection import PromptInjectionDetector, ThreatLevel

from app.integrations.providers import llm_summarize

# Indian PII patterns AGT's redactor does not ship. Masked in addition to the
# matches CredentialRedactor finds (email, card, AWS keys, etc.).
_INDIAN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("Aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("Indian phone", re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)")),
]

# Threat levels at or above which we block the run.
_BLOCK_LEVELS = {ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL}


@dataclass
class IntakeResult:
    """Outcome of the intake gate."""

    ok: bool                       # True if the run may proceed
    original_len: int
    clean_query: str               # PII-redacted query
    redactions: list[dict[str, Any]] = field(default_factory=list)
    injection_detected: bool = False
    injection_threat: str = "none"
    injection_reason: str = ""
    injection_patterns: list[str] = field(default_factory=list)
    company: str | None = None
    symbol: str | None = None
    block_reason: str | None = None
    # Prompt-defense posture of the submitted (PII-redacted) text, graded against
    # the 17 OWASP LLM/Agentic defense vectors. Informational only — never gates
    # the run. A normal user query grades low (D/F) by design.
    defense_grade: str = ""
    defense_score: int = 0
    defense_total: int = 0
    defense_missing: list[str] = field(default_factory=list)
    defense_top_findings: list[dict] = field(default_factory=list)


class Intake:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._injection = PromptInjectionDetector()
            self._defense = PromptDefenseEvaluator()
        self._nse_df = None  # lazy-loaded NSE equity master

    # -- PII redaction ----------------------------------------------------
    def _redact(self, text: str) -> tuple[str, list[dict]]:
        spans: list[tuple[int, int, str]] = []
        redactions: list[dict] = []

        # AGT-found PII spans (email, phone, card, ...).
        try:
            for m in CredentialRedactor.find_pii_matches(text):
                spans.append((m.start, m.end, m.name))
                redactions.append({"type": m.name, "value": _mask(m.matched_text)})
        except Exception:
            pass

        # AGT-detected credential *types* (AWS keys, tokens) — redact via its own call.
        try:
            types = CredentialRedactor.detect_credential_types(text)
            for t in types:
                redactions.append({"type": t, "value": "***"})
        except Exception:
            types = []

        # Indian patterns AGT doesn't ship.
        for name, pat in _INDIAN_PATTERNS:
            for mt in pat.finditer(text):
                spans.append((mt.start(), mt.end(), name))
                redactions.append({"type": name, "value": _mask(mt.group(0))})

        # Mask all spans (right-to-left so offsets stay valid), then run AGT's
        # own redact() to catch credential types it masks directly.
        clean = text
        for start, end, _name in sorted(set(spans), key=lambda s: s[0], reverse=True):
            clean = clean[:start] + "[REDACTED]" + clean[end:]
        try:
            clean = CredentialRedactor.redact(clean)
        except Exception:
            pass

        # De-dup redactions by (type, value).
        seen = set()
        uniq = []
        for r in redactions:
            key = (r["type"], r["value"])
            if key not in seen:
                seen.add(key)
                uniq.append(r)
        return clean, uniq

    # -- injection scan ---------------------------------------------------
    def _scan_injection(self, text: str):
        return self._injection.detect(text)

    # -- prompt-defense posture ------------------------------------------
    def _defense_grade(self, text: str) -> dict[str, Any]:
        """Grade the (clean) text against the 17 OWASP defense vectors.

        Pure static analysis, informational only. Guarded so a failure never
        breaks intake — on error, callers keep the safe defaults.
        """
        out: dict[str, Any] = {
            "defense_grade": "",
            "defense_score": 0,
            "defense_total": 0,
            "defense_missing": [],
            "defense_top_findings": [],
        }
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                report = self._defense.evaluate(text)
            out["defense_grade"] = report.grade
            out["defense_score"] = report.score
            out["defense_total"] = report.total
            out["defense_missing"] = list(report.missing)

            findings = getattr(report, "findings", None) or []
            top: list[dict] = []
            for f in findings:
                if getattr(f, "defended", True):
                    continue
                top.append({
                    "vector_id": getattr(f, "vector_id", ""),
                    "name": getattr(f, "name", ""),
                    "owasp": getattr(f, "owasp", ""),
                    "severity": getattr(f, "severity", ""),
                })
                if len(top) >= 6:
                    break
            if not top:
                # Fall back to the plain missing list if findings aren't rich.
                top = [{"vector_id": vid, "name": "", "owasp": "", "severity": ""}
                       for vid in out["defense_missing"][:6]]
            out["defense_top_findings"] = top
        except Exception:
            pass
        return out

    # -- NSE symbol resolution -------------------------------------------
    def _load_nse(self):
        if self._nse_df is not None:
            return self._nse_df
        try:
            import pandas as pd

            url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
            self._nse_df = pd.read_csv(url)
        except Exception:
            self._nse_df = False  # sentinel: unavailable
        return self._nse_df

    def _llm_company(self, query: str) -> str | None:
        """Ask the LLM to extract just the company name from the query."""
        resp = llm_summarize(
            "Extract ONLY the company name the user wants analyzed from this "
            "request. Reply with just the company name, nothing else. "
            f"Request: {query!r}"
        )
        text = (resp.get("text") or "").strip().strip('".')
        # Guard against a chatty model: take the first line, cap length.
        return text.splitlines()[0][:60] if text else None

    def _resolve_symbol(self, company: str | None) -> str | None:
        if not company:
            return None
        df = self._load_nse()
        if df is False or df is None:
            # NSE master unavailable — fall back to an uppercase heuristic.
            return re.sub(r"[^A-Z]", "", company.upper())[:12] or None
        try:
            name = company.lower().strip()
            matches = df[df["NAME OF COMPANY"].fillna("").str.lower().str.contains(name, regex=False)]
            if matches.empty:
                # try first word
                first = name.split()[0] if name.split() else name
                matches = df[df["NAME OF COMPANY"].fillna("").str.lower().str.contains(first, regex=False)]
            if not matches.empty:
                return str(matches.iloc[0]["SYMBOL"])
        except Exception:
            pass
        return None

    # -- public -----------------------------------------------------------
    def process(self, query: str) -> IntakeResult:
        with self._lock:
            clean, redactions = self._redact(query)

            # Grade the clean (PII-redacted) text's prompt-defense posture.
            # Informational only — never fed raw PII, never gates the run.
            defense = self._defense_grade(clean)

            det = self._scan_injection(query)
            threat = getattr(det.threat_level, "value", "none")
            blocked = det.is_injection and det.threat_level in _BLOCK_LEVELS
            if blocked:
                return IntakeResult(
                    ok=False,
                    original_len=len(query),
                    clean_query=clean,
                    redactions=redactions,
                    injection_detected=True,
                    injection_threat=threat,
                    injection_reason=det.explanation,
                    injection_patterns=list(det.matched_patterns),
                    block_reason=f"Prompt injection detected ({threat}): {det.explanation}",
                    **defense,
                )

            company = self._llm_company(clean)
            symbol = self._resolve_symbol(company)
            return IntakeResult(
                ok=True,
                original_len=len(query),
                clean_query=clean,
                redactions=redactions,
                injection_detected=det.is_injection,
                injection_threat=threat,
                injection_reason=det.explanation,
                injection_patterns=list(det.matched_patterns),
                company=company,
                symbol=symbol,
                **defense,
            )


def _mask(value: str) -> str:
    """Show only the shape of a secret, never the value."""
    v = value.strip()
    if len(v) <= 4:
        return "***"
    return f"{v[:2]}…{v[-2:]}"


intake = Intake()
