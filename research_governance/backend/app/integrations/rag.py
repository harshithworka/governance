# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""RAG over NSE annual reports (Indian stocks).

Pipeline for a given NSE symbol + query:

    NSE symbol -> fetch annual-report metadata -> download the latest PDF
    -> extract text (pypdf) -> chunk -> embed (Gemini) -> store in ChromaDB
    -> retrieve the top-k chunks most relevant to the query.

Everything external is best-effort with graceful fallback: if NSE blocks the
request, the PDF can't be parsed, or embeddings fail, the retriever returns an
empty result with a reason instead of raising — the desk then proceeds on
headlines + price alone (a "degraded" run), which is logged.

Local, free stack: ChromaDB (embedded, on-disk) + Gemini embeddings (free tier,
uses the GEMINI_API_KEY already in .env). Downloaded PDFs are cached on disk so
we never re-download.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import app.config  # noqa: F401
from app.config import settings

_CACHE_DIR = Path(__file__).resolve().parents[1] / "_rag_cache"
_REPORTS_DIR = _CACHE_DIR / "reports"
_CHROMA_DIR = _CACHE_DIR / "chroma"
for _d in (_REPORTS_DIR, _CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 150
_TOP_K = 4
_MAX_CHUNKS_INDEXED = 60   # cap embedding calls per report (free-tier friendly)


@dataclass
class RagResult:
    """Outcome of a retrieval."""

    available: bool                 # did we retrieve any grounded context?
    symbol: str
    source: str                     # "live" | "cache" | "unavailable"
    report_url: str | None = None
    chunks: list[str] = field(default_factory=list)
    reason: str = ""


def _nse_session():
    import requests

    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    s.get("https://www.nseindia.com/", timeout=20)  # obtain cookies
    return s


def _latest_report_url(symbol: str) -> str | None:
    """Return the newest annual-report PDF URL for an NSE symbol, or None."""
    try:
        s = _nse_session()
        r = s.get(
            "https://www.nseindia.com/api/annual-reports",
            params={"index": "equities", "symbol": symbol}, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("data") or data.get("reports") or []
        for row in rows:
            url = row.get("fileName") or row.get("file") or row.get("url")
            if url and str(url).lower().endswith(".pdf"):
                return url
    except Exception:
        return None
    return None


def _download_pdf(url: str, symbol: str) -> Path | None:
    name = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = _REPORTS_DIR / f"{symbol}_{name}.pdf"
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        import requests

        s = _nse_session()
        resp = s.get(url, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return path
    except Exception:
        return None


def _extract_chunks(pdf_path: Path) -> list[str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return []
    text = " ".join(text.split())
    chunks: list[str] = []
    i = 0
    while i < len(text) and len(chunks) < _MAX_CHUNKS_INDEXED:
        chunks.append(text[i : i + _CHUNK_SIZE])
        i += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def _embed(texts: list[str]) -> list[list[float]] | None:
    """Embed texts with Gemini. Returns None on any failure."""
    if not settings.gemini_api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        out: list[list[float]] = []
        for t in texts:
            res = genai.embed_content(model="models/gemini-embedding-001", content=t)
            out.append(res["embedding"])
        return out
    except Exception:
        return None


class RagStore:
    """ChromaDB-backed retriever, one collection per symbol."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client = None

    def _chroma(self):
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        return self._client

    def _collection_name(self, symbol: str) -> str:
        return "report_" + "".join(c for c in symbol.lower() if c.isalnum())[:40]

    def _ensure_indexed(self, symbol: str) -> tuple[bool, str, str | None]:
        """Make sure a collection for the symbol exists and is populated.

        Returns (indexed, source, report_url).
        """
        client = self._chroma()
        name = self._collection_name(symbol)
        existing = {c.name for c in client.list_collections()}
        if name in existing:
            coll = client.get_collection(name)
            if coll.count() > 0:
                return True, "cache", None

        url = _latest_report_url(symbol)
        if not url:
            return False, "unavailable", None
        pdf = _download_pdf(url, symbol)
        if not pdf:
            return False, "unavailable", url
        chunks = _extract_chunks(pdf)
        if not chunks:
            return False, "unavailable", url
        embeddings = _embed(chunks)
        if embeddings is None:
            return False, "unavailable", url

        coll = client.get_or_create_collection(name)
        coll.add(
            ids=[f"{name}_{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
        )
        return True, "live", url

    def retrieve(self, symbol: str, query: str) -> RagResult:
        with self._lock:
            try:
                indexed, source, url = self._ensure_indexed(symbol)
            except Exception as e:
                return RagResult(available=False, symbol=symbol, source="unavailable",
                                 reason=f"RAG error: {e}")
            if not indexed:
                return RagResult(available=False, symbol=symbol, source=source,
                                 report_url=url,
                                 reason="No annual report available (NSE blocked, "
                                        "parse failed, or embeddings unavailable)")
            q_emb = _embed([query])
            if q_emb is None:
                return RagResult(available=False, symbol=symbol, source=source,
                                 report_url=url, reason="query embedding failed")
            coll = self._chroma().get_collection(self._collection_name(symbol))
            res = coll.query(query_embeddings=q_emb, n_results=_TOP_K)
            docs = (res.get("documents") or [[]])[0]
            return RagResult(available=bool(docs), symbol=symbol, source=source,
                             report_url=url, chunks=docs,
                             reason="retrieved" if docs else "no matching chunks")


rag_store = RagStore()
