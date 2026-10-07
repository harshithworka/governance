# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""External providers with graceful mock fallbacks.

Phase 1 runs with **no API keys**: research and market data return deterministic
mock payloads so the governed desk works end to end offline. When keys are set
in ``.env`` (as you obtain them), the live paths activate automatically.

- Research  : Tavily  (``TAVILY_API_KEY``)   -> mock headlines otherwise
- Market    : Finnhub (``FINNHUB_API_KEY``)  -> mock quote otherwise
- LLM       : Groq    (``GROQ_API_KEY``)      -> templated text otherwise

Each function returns a dict plus a ``source`` field ("live" or "mock") so the
UI can show whether the data was real.
"""

from __future__ import annotations

import random
from typing import Any

from app.config import settings

# Deterministic-ish mock data keyed by symbol so demo runs are stable-ish.
_MOCK_HEADLINES = {
    "AAPL": ["Apple unveils new chip", "Analysts raise AAPL target", "Supply chain steady"],
    "TSLA": ["Tesla deliveries beat", "EV competition heats up", "Margins under pressure"],
    "NVDA": ["NVDA demand surges", "Data-center growth strong", "Valuation debate continues"],
}


_POS_WORDS = ("surge", "beat", "raise", "up", "growth", "strong", "gain", "record", "upgrade", "rally")
_NEG_WORDS = ("fall", "miss", "cut", "down", "weak", "loss", "drop", "probe", "lawsuit", "downgrade", "slump")


def _keyword_sentiment(texts: list[str]) -> float:
    """Cheap lexical sentiment in [-1, 1] over headline/snippet text."""
    blob = " ".join(texts).lower()
    pos = sum(blob.count(w) for w in _POS_WORDS)
    neg = sum(blob.count(w) for w in _NEG_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


def research_headlines(symbol: str, query: str | None = None) -> dict[str, Any]:
    """Return news + lexical sentiment for a symbol. Live via Tavily if a key is set."""
    if settings.has_research:
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=settings.tavily_api_key)
            q = query or f"{symbol} stock news latest"
            resp = client.search(q, max_results=5, topic="news")
            results = resp.get("results", [])
            headlines = [r.get("title", "") for r in results]
            snippets = [r.get("content", "") for r in results]
            return {
                "symbol": symbol,
                "headlines": headlines,
                "snippets": snippets,
                "sentiment": _keyword_sentiment(headlines + snippets),
                "source": "live",
            }
        except Exception as e:
            return {"symbol": symbol, "headlines": [], "sentiment": 0.0,
                    "source": "live-error", "error": str(e)}

    headlines = _MOCK_HEADLINES.get(symbol, [f"{symbol}: steady trading", f"{symbol}: mixed signals"])
    return {"symbol": symbol, "headlines": headlines,
            "sentiment": _keyword_sentiment(headlines), "source": "mock"}


def _finnhub_symbol(symbol: str) -> str:
    """Map a bare NSE ticker to Finnhub's NSE form (e.g. HDFCBANK -> HDFCBANK.NS).

    Leaves symbols that already carry an exchange suffix (a dot) untouched.
    """
    s = symbol.strip().upper()
    return s if "." in s else f"{s}.NS"


def market_quote(symbol: str) -> dict[str, Any]:
    """Return a quote for a symbol. Live via Finnhub if a key is set.

    NSE tickers are queried in Finnhub's ``SYMBOL.NS`` form. Finnhub's free tier
    may not return Indian quotes; if the live price comes back empty/zero we fall
    back to a mock price so the desk still has a number to reason about.
    """
    if settings.has_market_data and settings.finnhub_api_key:
        try:
            import httpx

            r = httpx.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": _finnhub_symbol(symbol), "token": settings.finnhub_api_key},
                timeout=10,
            )
            data = r.json()
            price = data.get("c")
            if price:  # non-zero, non-null → real live quote
                return {
                    "symbol": symbol,
                    "price": price,
                    "change_pct": data.get("dp"),
                    "source": "live",
                }
            # Finnhub free tier returned nothing for this NSE symbol → mock price.
            return {"symbol": symbol, "price": round(random.uniform(100, 4000), 2),
                    "change_pct": round(random.uniform(-5, 5), 2), "source": "mock-fallback"}
        except Exception as e:
            return {"symbol": symbol, "price": round(random.uniform(100, 4000), 2),
                    "change_pct": round(random.uniform(-5, 5), 2),
                    "source": "mock-fallback", "error": str(e)}

    price = round(random.uniform(100, 4000), 2)
    return {"symbol": symbol, "price": price, "change_pct": round(random.uniform(-5, 5), 2), "source": "mock"}


def llm_summarize(prompt: str) -> dict[str, Any]:
    """Summarize via Groq, falling back to Gemini, then a templated response."""
    if settings.groq_api_key:
        try:
            from groq import Groq

            client = Groq(api_key=settings.groq_api_key)
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return {"text": resp.choices[0].message.content, "source": "live", "model": settings.groq_model}
        except Exception as e:
            groq_err = str(e)
            # fall through to Gemini
            if not settings.gemini_api_key:
                return {"text": "", "source": "live-error", "error": groq_err}

    if settings.gemini_api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            return {"text": resp.text, "source": "live", "model": "gemini-1.5-flash"}
        except Exception as e:
            return {"text": "", "source": "live-error", "error": str(e)}

    return {"text": f"[mock summary] {prompt[:160]}", "source": "mock"}
