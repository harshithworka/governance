# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Desk routes — governed intake + a research→proposal→execution cycle."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings
from app.governance.intake import intake
from app.graph.desk_graph import run_desk
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


@router.get("/capabilities")
def capabilities() -> dict:
    """Report which live providers are enabled (based on which keys are set)."""
    return {
        "llm": settings.has_llm,
        "research": settings.has_research,
        "market_data": settings.has_market_data,
        "mode": "live" if (settings.has_llm or settings.has_research) else "mock",
    }
