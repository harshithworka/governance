# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Desk routes — governed intake + a research→proposal→execution cycle."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.governance.intake import intake
from app.graph.desk_graph import run_desk
from app.graph.desk_stream import run_desk_events
from app.store import db

router = APIRouter(prefix="/api/desk", tags=["desk"])


class IntakeRequest(BaseModel):
    query: str = Field(..., description="Free-text request, e.g. 'Analyze HDFC Bank'")


class RunRequest(BaseModel):
    symbol: str = Field(..., description="NSE ticker, e.g. HDFCBANK")
    amount: float = Field(..., ge=0, description="Proposed trade size")
    query: str | None = Field(None, description="Redacted query driving RAG retrieval")


@router.post("/intake")
def desk_intake(req: IntakeRequest) -> dict:
    """Governed intake: redact PII, scan for injection (block on detection),
    and resolve the company to an NSE symbol. The run proceeds only if ``ok``.
    """
    result = intake.process(req.query)
    rec = asdict(result)
    db.add_intake_event(rec)
    return rec


@router.post("/run")
def run(req: RunRequest) -> dict:
    """Run one governed desk cycle and return the terminal state."""
    final = run_desk(req.symbol.strip().upper(), float(req.amount), query=req.query)
    return {
        "run_id": final.get("run_id"),
        "status": final.get("status"),
        "blocked_by": final.get("blocked_by"),
        "approval_id": final.get("approval_id"),
        "result": final.get("result"),
        "proposal": final.get("proposal"),
        "rag": final.get("rag"),
        "trace": final.get("trace", []),
    }


@router.get("/run-stream")
async def run_stream(
    symbol: str = Query(..., description="NSE ticker, e.g. HDFCBANK"),
    amount: float = Query(..., ge=0, description="Proposed trade size"),
    query: str | None = Query(None, description="Redacted query driving RAG retrieval"),
) -> StreamingResponse:
    """Run one governed desk cycle as a Server-Sent Events stream.

    Executes the SAME agents as ``/run`` but one at a time, emitting ordered
    lifecycle events (WORKFLOW_STARTED, then per agent AGENT_STARTED /
    AGENT_COMPLETED / JEV_STARTED / JEV_COMPLETED, then WORKFLOW_COMPLETED or a
    *_BLOCKED pair). The blocking agent + JEV work runs in a worker thread; its
    events are pumped onto an asyncio queue so the stream is truly progressive.
    """
    sym = symbol.strip().upper()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def _produce() -> None:
        try:
            for event in run_desk_events(sym, float(amount), query=query):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:  # pragma: no cover - defensive
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "WORKFLOW_BLOCKED", "blocked_by": sym,
                 "stage": "error", "reason": str(e)},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    async def _event_source():
        # Kick off the (blocking) run in a worker thread.
        loop.run_in_executor(None, _produce)
        while True:
            event = await queue.get()
            if event is _DONE:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/capabilities")
def capabilities() -> dict:
    """Report which live providers are enabled (based on which keys are set)."""
    return {
        "llm": settings.has_llm,
        "research": settings.has_research,
        "market_data": settings.has_market_data,
        "jev": settings.has_jev,
        "mode": "live" if (settings.has_llm or settings.has_research) else "mock",
    }
