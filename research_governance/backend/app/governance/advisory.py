# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Advisory layer — a probabilistic classifier on top of deterministic policy.

The deterministic ``PolicyEngine`` decides allow / deny / require_approval. The
advisory layer runs *only after* a deterministic **allow** and can **tighten**
that outcome — never loosen it:

  - ``allow``            → pass through unchanged
  - ``flag_for_review``  → still allowed, but recorded as flagged for a human
  - ``block``            → the allow is downgraded to a deny (clearly marked as
                           an advisory, non-deterministic decision)

This mirrors how AGT's ``govern()`` runs its advisory check, and it is exactly
where a specialized "System 1" decision model (e.g. a Jev/Laya-style typed
decision model) would plug in: swap the heuristic ``_score_trade`` body for a
call to that model and return its typed verdict + confidence. We keep a
deterministic heuristic here so the demo runs offline and reproducibly.

FEATURES.md rows exercised: **Advisory layer**.
"""

from __future__ import annotations

from typing import Any

import app.config  # noqa: F401
from agentmesh.governance.advisory import AdvisoryDecision, CallbackAdvisory

# Thresholds for the demo heuristic.
_LARGE_TRADE = 50_000          # trades above this get extra scrutiny
_WATCH_INSTRUMENTS = {"MEME", "PENNY", "LEVERAGED"}  # noisy/volatile tickers
_NEGATIVE_SENTIMENT = -0.3     # research sentiment below this is a red flag


def _score_trade(context: dict[str, Any]) -> AdvisoryDecision:
    """Heuristic trade-risk classifier.

    Looks at the action + the research/market signals carried in the context
    and returns a non-deterministic opinion. A real deployment would replace
    this body with a call to a System-1 decision model and map its typed
    output to ``AdvisoryDecision``.
    """
    action = context.get("action", {})
    if action.get("type") != "place_trade":
        return AdvisoryDecision(action="allow", reason="not a trade", confidence=1.0)

    amount = float(action.get("amount", 0) or 0)
    symbol = str(action.get("symbol", "")).upper()
    sentiment = context.get("signals", {}).get("sentiment")
    momentum = context.get("signals", {}).get("change_pct")

    reasons: list[str] = []
    risk = 0.0

    if amount >= _LARGE_TRADE:
        risk += 0.4
        reasons.append(f"large size ({amount:,.0f})")
    if symbol in _WATCH_INSTRUMENTS:
        risk += 0.4
        reasons.append(f"watchlist instrument {symbol}")
    if sentiment is not None and sentiment <= _NEGATIVE_SENTIMENT:
        risk += 0.4
        reasons.append(f"negative news sentiment ({sentiment})")
    if momentum is not None and float(momentum) <= -5:
        risk += 0.3
        reasons.append(f"sharp downward momentum ({momentum}%)")

    # Map accumulated risk to an advisory action. Confidence reflects how
    # strong the aggregate signal is.
    if risk >= 0.8:
        return AdvisoryDecision(
            action="block",
            reason="High combined risk: " + "; ".join(reasons),
            confidence=min(0.95, 0.5 + risk / 2),
        )
    if risk >= 0.4:
        return AdvisoryDecision(
            action="flag_for_review",
            reason="Elevated risk: " + "; ".join(reasons),
            confidence=min(0.9, 0.4 + risk / 2),
        )
    return AdvisoryDecision(
        action="allow",
        reason="No elevated risk signals",
        confidence=0.6,
    )


# The advisory classifier GovDesk uses. ``on_error="allow"`` = fail-open: a
# broken classifier can never block a deterministically-allowed action (the
# advisory layer may only tighten based on a *successful* opinion).
trade_advisory = CallbackAdvisory(_score_trade, name="trade-risk-heuristic", on_error="allow")
