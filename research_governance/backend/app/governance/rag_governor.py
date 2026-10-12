# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Governed RAG retrieval via AGT's ``RAGGovernor`` (full ``.wrap`` drop-in).

Replaces the hand-rolled per-chunk injection screening that used to live inline
in ``desk_graph.py`` with the real AGT RAG governance pipeline:

    collection ACL  ->  rate limit  ->  content scan (PII + injection per chunk)
                    ->  audit (JSON-lines)  ->  surviving docs only

``governed.invoke(query)`` returns ONLY the chunks that passed scanning; partial
blocks are filtered + logged, and ``ContentScanError`` is raised only when ALL
chunks are blocked. We catch the governance exceptions and degrade gracefully so
the agent never crashes.

Retrieval itself is NOT reimplemented here: we reuse ``RagStore`` for indexing
and wrap a thin ``ChromaRetrieverAdapter`` with the governor.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import app.config  # noqa: F401
from agent_rag_governance import RAGGovernor, RAGPolicy
from agent_rag_governance.exceptions import (
    CollectionDeniedError,
    ContentScanError,
    RateLimitExceededError,
)

from app.integrations.rag import ChromaRetrieverAdapter, rag_store

_AGENT_ID = "market-data-agent"
_MAX_RETRIEVALS_PER_MINUTE = 30

# Audit log under the backend cache dir (alongside the Chroma store).
_AUDIT_PATH = (
    Path(__file__).resolve().parents[1] / "_rag_cache" / "rag_audit.jsonl"
)
_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


class _RagGovernor:
    """Singleton wiring of ``RAGGovernor`` over the Chroma retriever adapter."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._governor: Optional[RAGGovernor] = None

    def _get_governor(self) -> RAGGovernor:
        if self._governor is None:
            policy = RAGPolicy(
                allowed_collections=None,          # all symbols permitted
                denied_collections=[],
                max_retrievals_per_minute=_MAX_RETRIEVALS_PER_MINUTE,
                rate_limit_window_seconds=60,
                content_policies=["block_pii", "block_injections"],
                audit_enabled=True,
                audit_log_path=str(_AUDIT_PATH),
            )
            self._governor = RAGGovernor(policy=policy, agent_id=_AGENT_ID)
        return self._governor

    def retrieve(self, symbol: str, query: str) -> dict:
        """Governed retrieval. Returns a dict, never raises.

        Keys: available(bool), chunks(list[str]), source(str),
        report_url(str|None), blocked_count(int), reason(str).
        """
        with self._lock:
            # 1) Ensure the symbol's report is indexed (reuse RagStore). This
            #    is where NSE fetch / PDF parse / embedding happen.
            try:
                indexed, source, url = rag_store.ensure_indexed(symbol)
            except Exception as exc:
                return {
                    "available": False, "chunks": [], "source": "unavailable",
                    "report_url": None, "blocked_count": 0,
                    "reason": f"RAG error: {exc}",
                }
            if not indexed:
                return {
                    "available": False, "chunks": [], "source": source,
                    "report_url": url, "blocked_count": 0,
                    "reason": "No annual report available (NSE blocked, parse "
                              "failed, or embeddings unavailable)",
                }

            # 2) Wrap the retriever adapter and run the governance pipeline.
            adapter = ChromaRetrieverAdapter(rag_store, symbol)
            collection = rag_store._collection_name(symbol)
            governed = self._get_governor().wrap(adapter, collection=collection)
            try:
                docs = governed.invoke(query)
            except ContentScanError as exc:
                # Every chunk was blocked by the content scanner.
                return {
                    "available": False, "chunks": [], "source": source,
                    "report_url": url, "blocked_count": 1,
                    "reason": f"all retrieved chunks blocked by content scan: {exc}",
                }
            except CollectionDeniedError as exc:
                return {
                    "available": False, "chunks": [], "source": source,
                    "report_url": url, "blocked_count": 0,
                    "reason": f"collection denied by RAG policy: {exc}",
                }
            except RateLimitExceededError as exc:
                return {
                    "available": False, "chunks": [], "source": source,
                    "report_url": url, "blocked_count": 0,
                    "reason": f"RAG rate limit exceeded: {exc}",
                }
            except Exception as exc:
                return {
                    "available": False, "chunks": [], "source": source,
                    "report_url": url, "blocked_count": 0,
                    "reason": f"governed retrieval error: {exc}",
                }

            # Surviving docs → page_content strings. The governor filters
            # blocked chunks silently, so blocked_count is retrieved - surviving.
            surviving = [getattr(d, "page_content", str(d)) for d in docs]
            total = _retrieve_total(adapter, query)
            blocked_count = max(0, total - len(surviving))
            return {
                "available": bool(surviving),
                "chunks": surviving,
                "source": source,
                "report_url": url,
                "blocked_count": blocked_count,
                "reason": "retrieved" if surviving else "no surviving chunks",
            }


def _retrieve_total(adapter: ChromaRetrieverAdapter, query: str) -> int:
    """How many chunks the retriever returned pre-scan (for blocked_count).

    Cheap re-query of the already-indexed collection; degrades to the surviving
    count's floor on any error (so blocked_count never goes negative).
    """
    try:
        return len(adapter.invoke(query))
    except Exception:
        return 0


_rag_governor = _RagGovernor()


def governed_retrieve(symbol: str, query: str) -> dict:
    """Govern a RAG retrieval for *symbol* / *query*. Never raises.

    Returns {available, chunks, source, report_url, blocked_count, reason}.
    """
    return _rag_governor.retrieve(symbol, query)
