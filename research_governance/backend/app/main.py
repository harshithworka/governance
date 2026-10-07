# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""GovDesk FastAPI application.

Bridges the React frontend to the in-process AGT governance stack. Governance
enforcement happens inside this process (the proven, deterministic path); the
API only exposes queries, the desk-run trigger, approvals, and a live decision
stream over WebSocket.

Run (from research_governance/backend):
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_approvals, routes_desk, routes_governance
from app.config import settings
from app.governance.gate import gate
from app.store import db


def create_app() -> FastAPI:
    app = FastAPI(
        title="GovDesk API",
        version="0.1.0",
        description="Governed financial research desk — AGT governance in-process.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_desk.router)
    app.include_router(routes_governance.router)
    app.include_router(routes_approvals.router)

    # ------------------------------------------------------------------
    # Live decision stream.
    # The gate broadcasts from the (sync) graph thread; we hand each event
    # to the asyncio loop via a thread-safe queue and fan out to WS clients.
    # ------------------------------------------------------------------
    app.state.ws_clients = set()
    app.state.event_queue = None  # created on startup within the loop

    @app.on_event("startup")
    async def _startup() -> None:
        db.init_db()
        gate.setup()
        # Ensure the Phase 5 panels have data on first load (idempotent).
        try:
            from app.governance.discovery import discovery
            from app.governance.marketplace import marketplace

            marketplace.vet_catalog()
            discovery.scan()
        except Exception:
            pass
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        app.state.event_queue = queue

        def _on_decision(payload: dict) -> None:
            # Called from any thread -> schedule onto the loop safely.
            loop.call_soon_threadsafe(queue.put_nowait, payload)

        app.state._gate_listener = _on_decision
        gate.add_listener(_on_decision)

        async def _fanout() -> None:
            while True:
                payload = await queue.get()
                dead = []
                for ws in list(app.state.ws_clients):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    app.state.ws_clients.discard(ws)

        app.state._fanout_task = asyncio.create_task(_fanout())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        listener = getattr(app.state, "_gate_listener", None)
        if listener:
            gate.remove_listener(listener)
        task = getattr(app.state, "_fanout_task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "mode": "live" if settings.has_llm else "mock"}

    @app.websocket("/ws/decisions")
    async def ws_decisions(ws: WebSocket) -> None:
        await ws.accept()
        app.state.ws_clients.add(ws)
        try:
            while True:
                # We don't expect client messages; this keeps the socket open
                # and detects disconnects.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            app.state.ws_clients.discard(ws)

    return app


app = create_app()
