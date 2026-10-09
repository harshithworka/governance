# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Sequential, event-emitting desk run for the real-time pipeline UI.

This drives the SAME governed agent nodes as :mod:`app.graph.desk_graph`, but
runs them ONE AT A TIME so the frontend can render a strict sequential
pipeline. After each agent produces its output we run the JEV safety judge
(:mod:`app.governance.jev`) on that agent's REAL output; a live JEV score below
the threshold blocks the workflow and the next agent never starts. Real
governance blocks (deny / require_approval) from the gate still apply
independently of JEV.

No agent business logic or governance is reimplemented here: we call the exact
node functions (``research_node`` -> ``market_data_node`` -> ``strategy_node``
-> ``risk_node`` -> ``execution_node``) and read each agent's contribution from
``DeskState``. The 6th "governance" agent is monitor-only and is not part of
the executing pipeline; the stream ends with WORKFLOW_COMPLETED.

Events (JSON) are emitted in this exact order per run::

    WORKFLOW_STARTED
    for each agent in order:
        AGENT_STARTED
        AGENT_COMPLETED (with human-readable `output`)
        JEV_STARTED
        JEV_COMPLETED (score / safe / reason / source / model)
        [AGENT_BLOCKED + WORKFLOW_BLOCKED]  -> stop
    WORKFLOW_COMPLETED  (only if every agent passed)
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Iterator

from app.governance.gate import gate
from app.governance.jev import JEV_THRESHOLD, jev
from app.graph.desk_graph import (
    execution_node,
    market_data_node,
    research_node,
    risk_node,
    strategy_node,
)
from app.graph.state import DeskState

# The executing pipeline in strict order. (index, state-key, node fn, display)
_PIPELINE: list[tuple[str, Callable[[DeskState], DeskState], str]] = [
    ("research", research_node, "Research"),
    ("market_data", market_data_node, "Market-Data"),
    ("strategy", strategy_node, "Strategy"),
    ("risk", risk_node, "Risk Officer"),
    ("execution", execution_node, "Execution"),
]


def pipeline_agents() -> list[dict[str, Any]]:
    """The agent roster the UI should render up front (idle)."""
    return [
        {"index": i, "key": key, "name": name}
        for i, (key, _fn, name) in enumerate(_PIPELINE)
    ]


# ---------------------------------------------------------------------------
# Human-readable per-agent output summaries (fed to JEV + shown in the UI).
# ---------------------------------------------------------------------------
def _summarize(key: str, state: DeskState) -> tuple[str, dict[str, Any]]:
    """Return (readable_output_text, output_data) for an agent's contribution."""
    if key == "research":
        r = state.get("research", {}) or {}
        headlines = r.get("headlines", []) or []
        sentiment = r.get("sentiment")
        lines = "\n".join(f"- {h}" for h in headlines[:5]) or "- (no headlines)"
        text = (
            f"Research headlines for {state.get('symbol')}:\n{lines}\n"
            f"Sentiment: {sentiment} (source: {r.get('source')})"
        )
        return text, r

    if key == "market_data":
        m = state.get("market", {}) or {}
        rag = state.get("rag", {}) or {}
        rag_chunks = len(rag.get("chunks", []) or []) if rag.get("available") else 0
        text = (
            f"Price for {state.get('symbol')}: {m.get('price')} "
            f"(change {m.get('change_pct')}%, source: {m.get('source')}).\n"
            f"Annual-report RAG grounding: "
            f"{rag_chunks} chunk(s) used from {rag.get('source') or 'n/a'}."
        )
        return text, {"market": m, "rag": rag}

    if key == "strategy":
        p = state.get("proposal", {}) or {}
        thesis = p.get("thesis", "") or "(no thesis produced)"
        text = (
            f"Trade thesis ({p.get('side')} {p.get('symbol')} ₹{p.get('amount')}):\n"
            f"{thesis}\n"
            f"Grounded in annual report: {bool(p.get('grounded_in_report'))} "
            f"(source: {p.get('thesis_source')})"
        )
        return text, p

    if key == "risk":
        rk = state.get("risk", {}) or {}
        text = (
            f"Risk verdict: {rk.get('verdict')} "
            f"(rule: {rk.get('rule')}).\n{rk.get('reason') or ''}".strip()
        )
        return text, rk

    if key == "execution":
        status = state.get("status")
        if state.get("approval_id"):
            text = (
                "Execution requires human approval "
                f"(approval {state.get('approval_id')}). No order placed yet."
            )
            return text, {"status": status, "approval_id": state.get("approval_id")}
        res = state.get("result", {}) or {}
        if res.get("placed"):
            text = (
                f"SIMULATED order placed: {res.get('symbol')} ₹{res.get('amount')} "
                f"({res.get('note')})."
            )
        else:
            text = f"Execution outcome: {status} ({state.get('blocked_by') or 'n/a'})."
        return text, {"status": status, "result": res}

    return str(state.get(key, "")), {}


def _node_block_info(key: str, state: DeskState) -> tuple[str, str] | None:
    """If the node set a terminal block/approval status, return (reason, stage)."""
    status = state.get("status")
    if status == "blocked":
        return state.get("blocked_by") or f"{key}:blocked", "policy"
    if status == "pending_approval":
        return (
            f"{key}: human approval required (approval {state.get('approval_id')})",
            "approval",
        )
    return None


# ---------------------------------------------------------------------------
# The streaming generator (sync). Yields event dicts in order.
# ---------------------------------------------------------------------------
def run_desk_events(
    symbol: str, requested_amount: float, query: str | None = None
) -> Iterator[dict[str, Any]]:
    """Execute the desk sequentially, yielding ordered lifecycle events.

    This is a synchronous generator intended to be driven from a worker thread;
    the SSE endpoint pumps the yielded events onto an asyncio queue.
    """
    gate.setup()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    state: DeskState = {
        "run_id": run_id,
        "symbol": symbol,
        "requested_amount": requested_amount,
        "query": query or f"{symbol} revenue growth, risks, and outlook",
        "trace": [],
    }

    yield {
        "type": "WORKFLOW_STARTED",
        "run_id": run_id,
        "symbol": symbol,
        "query": state["query"],
        "agents": pipeline_agents(),
    }

    for index, (key, node_fn, name) in enumerate(_PIPELINE):
        yield {"type": "AGENT_STARTED", "index": index, "key": key, "name": name}

        # Run the REAL governed node. Guard so a crash becomes a clean block.
        try:
            state = node_fn(state)
        except Exception as e:  # pragma: no cover - defensive
            yield {
                "type": "AGENT_BLOCKED",
                "index": index,
                "key": key,
                "name": name,
                "reason": f"node error: {e}",
            }
            yield {
                "type": "WORKFLOW_BLOCKED",
                "blocked_by": name,
                "stage": "error",
                "run_id": run_id,
            }
            return

        output_text, output_data = _summarize(key, state)
        source = None
        if key == "research":
            source = (state.get("research") or {}).get("source")
        elif key == "market_data":
            source = (state.get("market") or {}).get("source")
        elif key == "strategy":
            source = (state.get("proposal") or {}).get("thesis_source")

        yield {
            "type": "AGENT_COMPLETED",
            "index": index,
            "key": key,
            "name": name,
            "output": output_text,
            "output_data": output_data,
            "source": source,
        }

        # Real governance block / approval wins and stops the pipeline.
        block = _node_block_info(key, state)
        if block is not None:
            reason, stage = block
            approval_id = state.get("approval_id") if stage == "approval" else None
            yield {
                "type": "AGENT_BLOCKED",
                "index": index,
                "key": key,
                "name": name,
                "reason": reason,
                "approval_id": approval_id,
            }
            yield {
                "type": "WORKFLOW_BLOCKED",
                "blocked_by": name,
                "stage": stage,
                "run_id": run_id,
                "approval_id": approval_id,
            }
            return

        # --- JEV safety judge on the REAL output -------------------------
        yield {"type": "JEV_STARTED", "index": index, "key": key, "name": name}
        verdict = jev.evaluate(name, output_text)
        yield {
            "type": "JEV_COMPLETED",
            "index": index,
            "key": key,
            "name": name,
            "score": verdict.get("score"),
            "safe": verdict.get("safe"),
            "reason": verdict.get("reason"),
            "source": verdict.get("source"),
            "model": verdict.get("model"),
        }

        # Only a live score below threshold blocks. unavailable/error are
        # non-blocking (shown honestly in the UI).
        if verdict.get("source") == "live" and verdict.get("safe") is False:
            score = verdict.get("score")
            yield {
                "type": "AGENT_BLOCKED",
                "index": index,
                "key": key,
                "name": name,
                "reason": f"JEV unsafe (score {score})",
            }
            yield {
                "type": "WORKFLOW_BLOCKED",
                "blocked_by": name,
                "stage": "jev",
                "run_id": run_id,
            }
            return

    yield {"type": "WORKFLOW_COMPLETED", "run_id": run_id, "status": "completed"}


# Expose the threshold for callers/tests.
__all__ = ["run_desk_events", "pipeline_agents", "JEV_THRESHOLD"]
