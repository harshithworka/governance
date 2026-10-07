<!-- Copyright (c) Microsoft Corporation. Licensed under the MIT License. -->
# GovDesk — Governed Financial Research Desk (Phase 1)

A multi-agent financial research desk that demonstrates the **Agent Governance
Toolkit (AGT)** end to end. Every agent action is checked by a deterministic
policy engine, attributed to a cryptographic agent identity, recorded in a
tamper-evident audit log, and scored by a behavioral trust engine. A React
**Agent Governance** page shows the complete agent history in real time.

> **Demonstration only — not a real trading system.** The Execution agent
> targets a *simulated/paper broker* and never places real orders. Not financial advice.

See [`plan.md`](./plan.md) for the full design and the later phases.

---

## What this demonstrates

### Phase 1 — core governance

| AGT feature | Where you see it |
|-------------|------------------|
| **Policy engine** (`PolicyEngine`) | Every agent action → allow / deny / require_approval |
| **Policy DSL** (numeric, compound, membership) | Risk limits, blocked instruments, approval thresholds |
| **Rate limiting** | Per-agent action caps in the policy YAMLs |
| **require_approval** | High-value trades route to the human approvals queue |
| **Agent identity** (`AgentIdentity`, Ed25519 DIDs) | Each agent has a `did:mesh:…` identity |
| **Audit log** (`AuditLog`, Merkle hash chain) | Tamper-evident trail + "Verify integrity" button |
| **Trust scoring** (`RewardEngine`) | Agents gain/lose trust from their decisions; auto-suspend on collapse |

### Phase 2 — MCP tool security

| AGT feature | Where you see it |
|-------------|------------------|
| **MCP Security Scanner** (`MCPSecurityScanner`) | Every market-data tool is screened for tool poisoning, hidden instructions, typosquatting, and rug-pulls |
| **Security gate (load-bearing)** | A tool with a CRITICAL finding is **blocked** — the Market-Data agent can only use tools that passed screening |
| **Rug-pull re-check** | Each use re-verifies the tool definition hasn't silently changed since approval |
| **Security panel** | The Agent Governance page shows per-tool verdicts (clean / flagged / blocked) and a "Re-scan catalog" button |

The MCP tool catalog (`backend/app/mcp/catalog.py`) includes two **intentionally
malicious demo tools** so the scanner has real threats to catch:
- `market_quote_pro` — a *poisoned* tool with a hidden instruction in its
  description → detected as **CRITICAL** and **blocked**.
- `finnhub_qoute` — a *typosquat* of `finnhub_quote` → **flagged** (warning).

The real `finnhub_quote` tool passes screening, so the Market-Data agent uses it
to fetch the live quote. The poisoned tool is structurally prevented from ever
influencing a trade.

### Phase 3 — runtime hardening

| AGT feature | Where you see it |
|-------------|------------------|
| **Execution rings** (`RingEnforcer`) | Each agent is pinned to a ring; the Execution/Risk/Strategy agents run in **RING_3_SANDBOX** (no network, no subprocess), Research/Market-Data in **RING_2_STANDARD** (network allowed). A node is blocked if its ring forbids the resource it needs. |
| **Command denylist** | Shell commands like `curl`/`wget`/`nc`/`bash` are structurally blocked — try the "Simulate egress attempt" button in the Runtime panel. |
| **Kill switch** (`KillSwitch`) | "Kill" an agent from the roster → real `KillResult` recorded in the kill history. |
| **Circuit breaker + SLO** (`CircuitBreaker`) | Live provider calls run through a per-agent breaker; repeated failures trip it OPEN and block further calls. Success rate is tracked per agent. |
| **Runtime panel** | The Agent Governance page shows ring assignments, breaker states, kill history, and a runtime event log (ring/command denials, breaker trips, kills). |

### Phase 4 — advisory layer (probabilistic, on top of deterministic)

| AGT feature | Where you see it |
|-------------|------------------|
| **Advisory layer** (`CallbackAdvisory`) | A probabilistic classifier runs **after** the deterministic allow on a trade and may only **tighten** it: `flag_for_review` (allowed but flagged) or `block` (the allow is downgraded to a deny, clearly marked non-deterministic). It can never loosen a deny. |
| **Advisory panel** | The Agent Governance page lists trades the advisory flagged or blocked, with confidence and reason. |

The demo classifier is a transparent heuristic (large size + watchlist instrument + negative
sentiment + sharp downward momentum). This is exactly where a specialized **System-1 decision
model** (e.g. a Jev/Laya-style typed decision model) would plug in — swap the heuristic body for a
model call and map its typed verdict + confidence to the advisory decision. Example runs:

- `MEME $60,000` → deterministic allow, then **advisory block** (watchlist + size).
- `AAPL $60,000` → deterministic allow, then **advisory flag** (size), trade still placed.

### Phase 5 — shadow discovery + marketplace vetting

| AGT feature | Where you see it |
|-------------|------------------|
| **Shadow AI Discovery** (`agent_discovery`) | Agents found running are reconciled against the governed registry. Ones with no identity/owner are flagged **shadow** (ungoverned) and risk-scored. The demo plants a rogue trading bot, an unknown MCP server, and an orphaned notebook agent — all surface as CRITICAL. |
| **Marketplace vetting** (`agent_marketplace`) | Each MCP data tool is vetted as a signed plugin: Ed25519 signature + verification, a trust tier, and a quality grade. A tool the MCP scan blocked is forced to the **revoked** tier — it cannot be trusted through the marketplace either. |
| **Shadow Discovery + Marketplace panels** | Two new panels on the Agent Governance page, each with a re-scan/re-vet button. |

Example: the poisoned `market_quote_pro` is **blocked** by the MCP scan *and* **revoked** by the
marketplace; `finnhub_quote` is clean, signed, verified, and trusted (tier `standard`).

### Phase 6 — governed intake + RAG over annual reports (Indian stocks)

| AGT feature | Where you see it |
|-------------|------------------|
| **Credential redactor** (`CredentialRedactor` + Indian PAN/Aadhaar/phone patterns) | A user's free-text request is PII-redacted before it is logged, displayed, or sent to the LLM. |
| **Prompt injection detector** (`PromptInjectionDetector`) | The request is scanned for injection; a detected attack (MEDIUM+ threat) **blocks the run** and shows the matched patterns. |
| **LLM symbol resolution** | The LLM extracts the company from the clean query; it's mapped to an NSE ticker via the NSE equity master. |
| **Governed RAG** (ChromaDB + Gemini embeddings) | The Market-Data agent's second tool retrieves passages from the company's **NSE annual report**; retrieved chunks are **injection-screened** before reaching the strategy LLM, and the retrieval is audited. |

The desk now starts from a **plain-English request** on the Desk page (e.g.
"Do a complete analysis of HDFC Bank. My phone is 9876543210"). Intake redacts
the phone/PAN/email, scans for injection, and resolves `HDFC Bank → HDFCBANK`.
Then the governed desk runs; the Strategy agent's thesis is **grounded in the
annual report** when retrieval succeeds.

- Clean request → PII redacted, symbol resolved, desk runs, thesis cites a report fundamental.
- Request containing "ignore all previous instructions…" → **blocked at intake** with the reason.
- Retrieved report chunks carrying injected instructions → **dropped** before the LLM, logged as `rag_injection_blocked`.

**RAG stack (free, local):** ChromaDB (embedded, on-disk) + Gemini embeddings
(`gemini-embedding-001`, uses the existing `GEMINI_API_KEY`). NSE report fetch is
best-effort and cached; if NSE is unavailable the desk degrades gracefully to
headlines + price.

> **New deps (Phase 6):** `chromadb`, `pypdf`, `pandas`. New env use: `GEMINI_API_KEY`
> is now also used for embeddings. Symbols are **Indian/NSE** (HDFCBANK, RELIANCE, TATAMOTORS).

Governance runs **in-process** in the backend (the deterministic guarantee).
LangGraph orchestrates the agent flow. The React app reads everything over REST
+ a live WebSocket decision stream.

> **Live data:** with API keys in `.env`, research (Tavily), market data
> (Finnhub), and the LLM (Groq, Gemini fallback) are all **live**. Only trade
> *placement* is simulated (paper broker).

**Phase 1 runs with no API keys** — research and market data use deterministic
mock payloads. Add keys later (see below) to turn on live providers.

---

## Architecture

```
React (Vite, :5173)  ──REST + WebSocket──►  FastAPI (:8099)
                                              │ LangGraph graph (research→market→strategy→risk→execution)
                                              │ AGT in-process: PolicyEngine · AuditLog · RewardEngine · AgentIdentity
                                              ▼
                                            SQLite (govdesk.db)
```

The 6 agents: **Research, Market-Data, Strategy, Risk Officer, Execution,
Governance/Discovery**. Each has its own policy in `backend/app/policies/*.yaml`.

---

## Prerequisites

- **Python 3.11+** (tested on 3.13)
- **Node 18+ / npm 9+** (tested on Node 24 / npm 11)
- The AGT source is imported from this repository's local tree automatically
  (`backend/app/config.py` adds `agent-governance-python/*/src` to `sys.path`),
  so you do **not** need to `pip install agent-governance-toolkit-core` separately.

---

## Run the backend

```bash
cd research_governance/backend
pip install -r requirements.txt          # fastapi, uvicorn, langgraph, etc.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
```

Backend is now at **http://127.0.0.1:8099** (interactive docs at `/docs`).

Quick check:

```bash
curl http://127.0.0.1:8099/api/health          # {"status":"ok","mode":"live"}  (with keys in .env)
```

## Run the frontend

In a second terminal:

```bash
cd research_governance/frontend
npm install
npm run dev                                # Vite dev server on :5173
```

Open **http://localhost:5173** → it redirects to the **Agent Governance** page.

---

## Try it

On the **Desk** page, run a cycle (or click a preset):

| Input | Expected outcome |
|-------|------------------|
| `AAPL`, `500` | ✅ **completed** — small trade, simulated order placed |
| `NVDA`, `150000` | ⏳ **pending_approval** — appears in the approvals queue |
| `SANCTIONED`, `1000` | ⛔ **blocked** at the Risk Officer (instrument blocklist) |
| `TSLA`, `300000` | ⛔ **blocked** at the Risk Officer (exceeds max size) |

Then open **Agent Governance** to watch, in real time:

- the **decision timeline** stream each agent's allow/deny/require_approval (live via WebSocket),
- the **approvals queue** — approve the NVDA trade to complete its (simulated) execution,
- the **audit trail** — click **Verify integrity** to confirm the hash chain,
- the **MCP tool security** panel — see the poisoned tool **blocked** and the
  typosquat **flagged**; click **Re-scan catalog** to re-run screening,
- the **Runtime hardening** panel — ring assignments, circuit-breaker states,
  kill history; click **Simulate egress attempt** to see the command denylist
  block a `curl` exfiltration,
- the **agent roster** — trust scores update; use **Kill** to terminate an agent
  via the real kill switch.

---

## Configuration (optional — Phase 1 needs none)

Copy `backend/.env.example` to `backend/.env` and fill in as you obtain keys:

| Variable | Enables |
|----------|---------|
| `GROQ_API_KEY` | Live LLM for the Strategy agent's thesis (Groq) |
| `GEMINI_API_KEY` | Fallback LLM |
| `TAVILY_API_KEY` | Live web/news research (Research agent) |
| `FINNHUB_API_KEY` | Live market quotes (Market-Data agent) |
| `ALPHAVANTAGE_API_KEY` | Fallback market data (25 calls/day) |
| `AGT_AUDIT_SECRET_KEY` | Persistent, HMAC-signed audit sink (hex, ≥32 bytes) |

When a key is present the matching provider switches from `mock` to `live`
automatically; the UI's backend badge shows the current mode. No code changes needed.

---

## Project layout

```
research_governance/
  plan.md                 full design + phases
  README.md               this file
  backend/
    app/
      config.py           AGT import bootstrap + settings
      store/db.py          SQLite store (agents, decisions, audit, trust, approvals)
      governance/
        identities.py      per-agent AgentIdentity (Ed25519 DIDs)
        gate.py            the governance gate: PolicyEngine + AuditLog + RewardEngine
        mcp_security.py    MCP tool screening (MCPSecurityScanner) — Phase 2
        rings.py           execution rings + command denylist (RingEnforcer) — Phase 3
        killswitch.py      agent termination (KillSwitch) — Phase 3
        reliability.py     circuit breakers + SLO (CircuitBreaker) — Phase 3
        advisory.py        probabilistic advisory classifier (CallbackAdvisory) — Phase 4
        discovery.py       shadow AI discovery + reconciliation (agent_discovery) — Phase 5
        marketplace.py     MCP tool vetting + signing (agent_marketplace) — Phase 5
        intake.py          governed intake: PII redaction + injection scan + symbol resolution — Phase 6
      integrations/rag.py  NSE annual-report RAG (ChromaDB + Gemini embeddings) — Phase 6
      mcp/catalog.py       MCP tool definitions (incl. demo-malicious tools) — Phase 2
      policies/*.yaml      one deterministic policy per agent
      graph/desk_graph.py  LangGraph agent flow + approval handling
      integrations/        LLM / research / market-data (mock-first)
      api/                 FastAPI routes (desk, governance, approvals) + WebSocket
      main.py              app factory + live decision stream
  frontend/
    src/
      pages/               Desk, AgentGovernance, Policies
      components/          AgentRoster, DecisionTimeline, AuditTrail, ApprovalsQueue, SecurityPanel,
                           RuntimePanel, AdvisoryPanel, ShadowDiscoveryPanel, MarketplacePanel,
                           IntakePanel, RagPanel
      lib/                 api.ts, ws.ts, types.ts
```

---

## Notes & limitations

- **Simulated execution only** — no real brokerage is ever contacted.
- **In-memory audit chain** by default (lost on restart). Set `AGT_AUDIT_SECRET_KEY`
  to also persist a signed audit file (Phase 2+ wiring).
- **Free-tier limits** apply to live providers; Alpha Vantage (25/day) is the
  deliberate fallback and drives the rate-limit demonstration.
- LangGraph prints a harmless deprecation warning on startup.
- This project lives under `research_governance/` and is self-contained; it does
  not modify the AGT core packages.
```
