# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Approvals routes — the human-in-the-loop queue for high-value trades."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.desk_graph import resume_after_approval
from app.store import db

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ResolveRequest(BaseModel):
    approved: bool
    resolver: str = "human"


@router.get("")
def list_approvals(status: str | None = None) -> dict:
    """List approvals; pass ?status=pending for the open queue."""
    return {"items": db.list_approvals(status=status)}


@router.post("/{approval_id}/resolve")
def resolve(approval_id: str, req: ResolveRequest) -> dict:
    """Approve or reject a pending high-value trade.

    On approval, the deterministic gate already decided ``require_approval``;
    a human sign-off here completes the (simulated) execution.
    """
    rec = db.resolve_approval(approval_id, req.approved, resolver=req.resolver)
    if not rec:
        raise HTTPException(404, "unknown or already-resolved approval")

    result = None
    if req.approved:
        result = resume_after_approval(approval_id)

    return {"approval_id": approval_id, "status": rec["status"], "result": result}
