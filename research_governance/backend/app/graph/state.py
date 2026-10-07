# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Shared state for the GovDesk LangGraph desk graph."""

from __future__ import annotations

from typing import Any, TypedDict


class DeskState(TypedDict, total=False):
    """State threaded through the desk graph.

    Each node reads what it needs and writes its contribution. Governance
    verdicts never live in the LLM-visible state — they are enforced in the
    nodes via the gate and recorded to the store.
    """

    run_id: str
    symbol: str                 # ticker under consideration
    requested_amount: float     # proposed trade size

    query: str                  # the (redacted) user query driving the run
    research: dict[str, Any]    # Research agent output
    market: dict[str, Any]      # Market-Data agent output
    rag: dict[str, Any]         # annual-report RAG result (chunks + provenance)
    proposal: dict[str, Any]    # Strategy agent output
    risk: dict[str, Any]        # Risk Officer output

    # Terminal outcome of the run
    status: str                 # completed | blocked | pending_approval
    blocked_by: str             # agent/action that blocked the run
    approval_id: str            # set when a human approval is required
    result: dict[str, Any]      # final execution result / summary
    trace: list[dict[str, Any]] # per-step human-readable trace
