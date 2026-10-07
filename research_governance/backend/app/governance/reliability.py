# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Reliability — per-agent circuit breakers + simple SLO counters (AGT SRE).

Wraps AGT's ``CircuitBreaker``. Each agent gets a breaker; provider calls run
through it. Repeated failures (e.g. a data source erroring) trip the breaker
OPEN, which then blocks further calls from that agent until it recovers — the
canonical SRE pattern that stops a failing dependency from cascading.

A lightweight SLO counter tracks success rate per agent for the UI.

FEATURES.md rows exercised: **Circuit breaker**, **SLO**.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import app.config  # noqa: F401
from agent_sre.cascade.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
)

from app.store import db


@dataclass
class _SLO:
    total: int = 0
    success: int = 0

    @property
    def success_rate(self) -> float:
        return (self.success / self.total) if self.total else 1.0


class Reliability:
    """Process-wide circuit breakers + SLO counters, keyed by agent."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._slo: dict[str, _SLO] = {}

    def _breaker(self, agent_key: str) -> CircuitBreaker:
        with self._lock:
            if agent_key not in self._breakers:
                self._breakers[agent_key] = CircuitBreaker(
                    agent_key,
                    CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=15.0),
                )
                self._slo[agent_key] = _SLO()
            return self._breakers[agent_key]

    def call(
        self,
        agent_key: str,
        fn: Callable[[], Any],
        *,
        agent_did: str = "",
        agent_name: str = "",
    ) -> tuple[bool, Any, str]:
        """Run ``fn`` through the agent's breaker.

        Returns (ok, result, reason). On an open circuit, ok=False and the call
        is NOT attempted. A failing fn records a failure and may trip the breaker.
        """
        breaker = self._breaker(agent_key)
        prev_state = breaker.state
        slo = self._slo[agent_key]
        try:
            result = breaker.call(fn)
        except CircuitOpenError as e:
            db.add_runtime_event(
                kind="breaker_open",
                agent_did=agent_did,
                agent_name=agent_name,
                detail=str(e),
                data={"retry_after": round(e.retry_after, 1)},
            )
            return False, None, f"circuit open: {e}"
        except Exception as e:  # noqa: BLE001 — provider failure
            slo.total += 1
            if breaker.state == "OPEN" and prev_state != "OPEN":
                db.add_runtime_event(
                    kind="breaker_open",
                    agent_did=agent_did,
                    agent_name=agent_name,
                    detail=f"breaker tripped after failure: {e}",
                    data={"failures": breaker.failure_count},
                )
            return False, None, f"provider error: {e}"
        slo.total += 1
        slo.success += 1
        return True, result, "ok"

    def record_failure(self, agent_key: str) -> None:
        """Force a failure (used to demo breaker tripping)."""
        self._breaker(agent_key).record_failure()

    def reset(self, agent_key: str) -> None:
        with self._lock:
            if agent_key in self._breakers:
                self._breakers[agent_key].reset()
                db.add_runtime_event(kind="breaker_reset", detail=agent_key)

    def states(self) -> list[dict]:
        """Breaker state + SLO per agent (for the UI)."""
        with self._lock:
            out = []
            for key, breaker in self._breakers.items():
                slo = self._slo.get(key, _SLO())
                out.append({
                    "agent_key": key,
                    "state": breaker.state,
                    "failures": breaker.failure_count,
                    "slo_total": slo.total,
                    "slo_success": slo.success,
                    "success_rate": round(slo.success_rate, 3),
                })
            return out


reliability = Reliability()
