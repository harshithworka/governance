# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""The GovDesk LangGraph desk graph.

Flow:  research -> market_data -> strategy -> risk -> execution -> END

Every node calls ``gate.evaluate`` for its agent BEFORE acting. The returned
verdict decides control flow:

- **allow**            : the node does its work and the graph proceeds.
- **deny**             : the run is blocked; graph routes to END with status
                         ``blocked`` (governance made the bad action impossible).
- **require_approval** : an approval record is created and the run halts with
                         status ``pending_approval`` for a human to resolve
                         (resumed via :func:`resume_after_approval`).

LangGraph owns orchestration/flow; AGT ``gate`` owns the allow/deny guarantee.
"""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from app.governance.gate import gate
from app.governance.mcp_security import mcp_security
from app.governance.reliability import reliability
from app.governance.rings import rings
from app.graph.state import DeskState
from app.integrations.providers import llm_summarize, market_quote, research_headlines
from app.integrations.rag import rag_store
from app.mcp.catalog import FALLBACK_TOOL, PREFERRED_TOOL
from app.store import db

# RAG retrieved chunks are untrusted content (classic indirect-injection vector),
# so each is screened before it can reach the strategy LLM.
import warnings as _warnings
with _warnings.catch_warnings():
    _warnings.simplefilter("ignore")
    from agent_os.prompt_injection import PromptInjectionDetector, ThreatLevel

_rag_injection_detector = PromptInjectionDetector()


def _trace(state: DeskState, step: str, detail: dict[str, Any]) -> None:
    state.setdefault("trace", []).append({"step": step, **detail})


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def research_node(state: DeskState) -> DeskState:
    symbol = state["symbol"]

    # 1) Policy gate
    v = gate.evaluate("research", {"type": "web_search", "symbol": symbol}, run_id=state["run_id"])
    if not v.allowed:
        state["status"] = "blocked"; state["blocked_by"] = f"research:{v.verdict}"
        _trace(state, "research", {"verdict": v.verdict, "reason": v.reason})
        return state

    # 2) Ring gate — research needs network (Tavily). RING_2 permits it.
    net_ok, net_reason = rings.check_resource("research", "network",
                                              agent_did=v.agent_did, agent_name=v.agent_name)
    if not net_ok:
        state["status"] = "blocked"; state["blocked_by"] = "research:ring_denied"
        _trace(state, "research", {"verdict": "deny", "reason": net_reason})
        return state

    # 3) Circuit breaker around the live provider call
    ok, data, reason = reliability.call(
        "research", lambda: research_headlines(symbol),
        agent_did=v.agent_did, agent_name=v.agent_name,
    )
    if not ok:
        state["status"] = "blocked"; state["blocked_by"] = "research:breaker"
        _trace(state, "research", {"verdict": "deny", "reason": reason})
        return state

    state["research"] = data
    _trace(state, "research", {"verdict": v.verdict, "source": data.get("source"),
                               "headlines": len(data.get("headlines", [])),
                               "ring": rings.ring_label("research")})
    return state


def market_data_node(state: DeskState) -> DeskState:
    symbol = state["symbol"]

    # 1) Policy gate — may this agent read market data at all?
    v = gate.evaluate("market_data", {"type": "read_market_data", "symbol": symbol}, run_id=state["run_id"])
    if not v.allowed:
        state["status"] = "blocked"; state["blocked_by"] = f"market_data:{v.verdict}"
        _trace(state, "market_data", {"verdict": v.verdict, "reason": v.reason})
        return state

    # 2) Ring gate — market-data needs network (Finnhub). RING_2 permits it.
    net_ok, net_reason = rings.check_resource("market_data", "network",
                                              agent_did=v.agent_did, agent_name=v.agent_name)
    if not net_ok:
        state["status"] = "blocked"; state["blocked_by"] = "market_data:ring_denied"
        _trace(state, "market_data", {"verdict": "deny", "reason": net_reason})
        return state

    # 3) MCP security gate — pick a tool that passed scanning (preferred, then
    # fallback). A poisoned/blocked tool is structurally unusable here.
    chosen = None
    for candidate in (PREFERRED_TOOL, FALLBACK_TOOL):
        allowed, reason = mcp_security.is_tool_allowed(candidate)
        if not allowed:
            _trace(state, "market_data", {"mcp_tool": candidate, "mcp_allowed": False, "reason": reason})
            continue
        # 3) Rug-pull recheck — did the tool's definition change since approval?
        rug = mcp_security.recheck_rug_pull(candidate)
        if rug is not None:
            _trace(state, "market_data", {"mcp_tool": candidate, "mcp_allowed": False,
                                          "reason": f"rug pull: {rug['message']}"})
            continue
        chosen = candidate
        break

    if chosen is None:
        state["status"] = "blocked"; state["blocked_by"] = "market_data:no_safe_mcp_tool"
        _trace(state, "market_data", {"verdict": "deny",
                                      "reason": "no MCP data tool passed security screening"})
        return state

    # 5) Use the governed tool to fetch the live quote, through the breaker.
    ok, quote, reason = reliability.call(
        "market_data", lambda: market_quote(symbol),
        agent_did=v.agent_did, agent_name=v.agent_name,
    )
    if not ok:
        state["status"] = "blocked"; state["blocked_by"] = "market_data:breaker"
        _trace(state, "market_data", {"verdict": "deny", "reason": reason})
        return state
    quote["mcp_tool"] = chosen
    state["market"] = quote
    _trace(state, "market_data", {"verdict": v.verdict, "price": quote.get("price"),
                                  "source": quote.get("source"), "mcp_tool": chosen})

    # 6) Second governed tool: RAG over the annual report (fundamentals).
    #    The tool must pass MCP security screening; retrieved chunks are then
    #    injection-screened before any can reach the strategy LLM.
    rag_tool = "annual_report_rag"
    rag_allowed, rag_reason = mcp_security.is_tool_allowed(rag_tool)
    if not rag_allowed:
        state["rag"] = {"available": False, "reason": rag_reason, "mcp_tool": rag_tool}
        _trace(state, "market_data", {"rag": "tool_blocked", "reason": rag_reason})
        return state

    query = state.get("query") or f"{symbol} revenue growth, risks, and outlook"
    rag_res = rag_store.retrieve(symbol, query)

    safe_chunks: list[str] = []
    flagged = 0
    for chunk in rag_res.chunks:
        det = _rag_injection_detector.detect(chunk)
        if det.is_injection and det.threat_level in (
            ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL
        ):
            flagged += 1
            db.add_runtime_event(
                kind="rag_injection_blocked",
                agent_did=v.agent_did, agent_name=v.agent_name,
                detail=f"Injected content in retrieved chunk: {det.explanation}",
                data={"symbol": symbol, "threat": det.threat_level.value},
            )
            continue
        safe_chunks.append(chunk)

    state["rag"] = {
        "available": rag_res.available and bool(safe_chunks),
        "symbol": symbol,
        "source": rag_res.source,
        "report_url": rag_res.report_url,
        "chunks": safe_chunks,
        "chunks_total": len(rag_res.chunks),
        "chunks_flagged": flagged,
        "reason": rag_res.reason,
        "mcp_tool": rag_tool,
    }
    # Persist the retrieval for the RAG panel.
    db.add_rag_retrieval(
        run_id=state["run_id"], symbol=symbol, source=rag_res.source,
        report_url=rag_res.report_url, chunks_total=len(rag_res.chunks),
        chunks_used=len(safe_chunks), chunks_flagged=flagged,
        available=state["rag"]["available"], reason=rag_res.reason,
    )
    # Audit the retrieval (what report, how many chunks, how many flagged).
    gate.evaluate(
        "market_data",
        {"type": "read_market_data", "symbol": symbol, "tool": "annual_report_rag",
         "chunks": len(safe_chunks), "flagged": flagged},
        run_id=state["run_id"], resource=rag_res.report_url or "nse-annual-report",
    )
    _trace(state, "market_data", {"rag_source": rag_res.source,
                                  "rag_chunks": len(safe_chunks),
                                  "rag_flagged": flagged,
                                  "rag_available": state["rag"]["available"]})
    return state


def strategy_node(state: DeskState) -> DeskState:
    symbol = state["symbol"]
    v = gate.evaluate("strategy", {"type": "draft_proposal", "symbol": symbol}, run_id=state["run_id"])
    if not v.allowed:
        state["status"] = "blocked"; state["blocked_by"] = f"strategy:{v.verdict}"
        _trace(state, "strategy", {"verdict": v.verdict, "reason": v.reason})
        return state
    amount = float(state.get("requested_amount", 0) or 0)
    rag = state.get("rag", {})
    rag_chunks = rag.get("chunks", []) if rag.get("available") else []
    # Only injection-screened chunks reach the LLM.
    rag_context = "\n".join(f"- {c[:400]}" for c in rag_chunks[:4])
    summary = llm_summarize(
        f"Draft a one-line trade thesis for {symbol}.\n"
        f"Headlines: {state.get('research', {}).get('headlines')}\n"
        f"Price: {state.get('market', {}).get('price')}\n"
        + (f"Grounding from the latest annual report:\n{rag_context}\n"
           if rag_context else "")
        + "Base the thesis on the data above; cite a fundamental if report "
          "grounding is present."
    )
    proposal = {
        "symbol": symbol,
        "amount": amount,
        "side": "buy",
        "thesis": summary.get("text", ""),
        "thesis_source": summary.get("source"),
        "grounded_in_report": bool(rag_chunks),
    }
    state["proposal"] = proposal
    _trace(state, "strategy", {"verdict": v.verdict, "amount": amount,
                               "grounded_in_report": bool(rag_chunks)})
    return state


def risk_node(state: DeskState) -> DeskState:
    proposal = state.get("proposal", {})
    action = {
        "type": "assess_trade",
        "amount": float(proposal.get("amount", 0) or 0),
        "instrument": proposal.get("symbol", "UNKNOWN"),
    }
    v = gate.evaluate("risk", action, run_id=state["run_id"])
    state["risk"] = {"verdict": v.verdict, "rule": v.matched_rule, "reason": v.reason}
    if not v.allowed:
        state["status"] = "blocked"; state["blocked_by"] = f"risk:{v.matched_rule}"
        _trace(state, "risk", {"verdict": v.verdict, "reason": v.reason})
        return state
    _trace(state, "risk", {"verdict": v.verdict})
    return state


def execution_node(state: DeskState) -> DeskState:
    proposal = state.get("proposal", {})
    amount = float(proposal.get("amount", 0) or 0)
    action = {"type": "place_trade", "amount": amount, "symbol": proposal.get("symbol")}
    # Soft signals for the probabilistic advisory layer (not used by the
    # deterministic policy engine).
    signals = {
        "sentiment": state.get("research", {}).get("sentiment"),
        "change_pct": state.get("market", {}).get("change_pct"),
    }
    v = gate.evaluate("execution", action, run_id=state["run_id"], signals=signals)

    if v.requires_approval:
        appr = db.add_approval(
            agent_did=v.agent_did,
            action="place_trade",
            reason=v.reason or "High-value trade requires approval",
            payload=proposal,
            run_id=state["run_id"],
        )
        state["status"] = "pending_approval"
        state["approval_id"] = appr["approval_id"]
        _trace(state, "execution", {"verdict": v.verdict, "approval_id": appr["approval_id"]})
        return state

    if not v.allowed:
        # Distinguish an advisory block from a policy deny.
        advisory = "[advisory" in (v.reason or "")
        state["status"] = "blocked"
        state["blocked_by"] = f"execution:{'advisory_block' if advisory else v.verdict}"
        _trace(state, "execution", {"verdict": v.verdict, "reason": v.reason,
                                    "advisory": advisory})
        return state

    # Simulated/paper execution only — never a real order.
    state["status"] = "completed"
    state["result"] = {"placed": True, "paper": True, "symbol": proposal.get("symbol"),
                       "amount": amount, "note": "SIMULATED order (paper broker)"}
    _trace(state, "execution", {"verdict": v.verdict, "placed": True, "paper": True,
                                "advisory_flag": "advisory flag" in (v.reason or "")})
    return state


# ---------------------------------------------------------------------------
# Routing: stop early if a node blocked or needs approval
# ---------------------------------------------------------------------------
def _route_after(node_next: str):
    def router(state: DeskState) -> str:
        if state.get("status") in ("blocked", "pending_approval"):
            return END
        return node_next
    return router


def build_graph():
    g = StateGraph(DeskState)
    g.add_node("research", research_node)
    g.add_node("market_data", market_data_node)
    g.add_node("strategy", strategy_node)
    g.add_node("risk", risk_node)
    g.add_node("execution", execution_node)

    g.set_entry_point("research")
    g.add_conditional_edges("research", _route_after("market_data"), {"market_data": "market_data", END: END})
    g.add_conditional_edges("market_data", _route_after("strategy"), {"strategy": "strategy", END: END})
    g.add_conditional_edges("strategy", _route_after("risk"), {"risk": "risk", END: END})
    g.add_conditional_edges("risk", _route_after("execution"), {"execution": "execution", END: END})
    g.add_edge("execution", END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_desk(symbol: str, requested_amount: float, query: str | None = None) -> DeskState:
    """Run one desk cycle. Returns the terminal state."""
    gate.setup()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    initial: DeskState = {
        "run_id": run_id, "symbol": symbol, "requested_amount": requested_amount,
        "query": query or f"{symbol} revenue growth, risks, and outlook",
        "trace": [],
    }
    final = get_graph().invoke(initial)
    final.setdefault("status", "completed")
    return final


def resume_after_approval(approval_id: str) -> dict[str, Any]:
    """Complete a trade after a human approved it (post-interrupt resume).

    The deterministic gate already decided ``require_approval``; a human then
    approved it. Here we record the simulated execution. If the human rejected,
    the caller does not invoke this.
    """
    appr = db.get_approval(approval_id)
    if not appr:
        return {"error": "unknown approval"}
    if appr["status"] != "approved":
        return {"error": f"approval not approved (status={appr['status']})"}
    proposal = appr.get("payload", {})
    return {
        "placed": True, "paper": True, "symbol": proposal.get("symbol"),
        "amount": proposal.get("amount"), "note": "SIMULATED order after human approval",
    }
