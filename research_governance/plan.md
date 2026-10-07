# GovDesk — Governed Financial Research & Trade-Proposal Desk

> A multi-agent financial research desk that demonstrates the **Agent Governance Toolkit (AGT)** end to end. Every agent action is governed by deterministic policy, cryptographically attributed, tamper-evidently audited, and behavior-scored. A React **Agent Governance** page shows the complete agent history in real time.
>
> **This is a demonstration, not a real trading system.** The Execution agent targets a *simulated/paper broker* and never places real orders.

---

## 1. Goal

Build a realistic multi-agent system where **AGT governance is load-bearing** — the project would be unsafe or broken without it — so each AGT feature has an obvious, honest reason to exist. Pair it with a modern React UI whose centerpiece is an **Agent Governance** page.

Non-goals: real brokerage integration, financial advice, production trading.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  React (Vite) frontend                                           │
│   • Desk page (research → proposal → approve)                    │
│   • Agent Governance page  ← the centerpiece                     │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ REST (queries/actions)         │ WebSocket (live decision stream)
                ▼                                 ▼
┌────────────────────────────────────────────────────────────────┐
│  FastAPI backend                                                 │
│   • LangGraph agent graph (orchestration + approval interrupts)  │
│   • AGT libraries called IN-PROCESS (the deterministic guarantee)│
│       govern() · PolicyEngine · AuditLog · RewardEngine ·        │
│       MCP scanner/gateway · RingEnforcer · KillSwitch            │
│   • Emits every decision/audit/trust event to the store         │
└───────────────┬───────────────────────────────┬─────────────────┘
                │                                 │
   external APIs▼                                 ▼ shared store
   Groq / Gemini (LLM)                   SQLite (dev) → Postgres (later)
   Tavily (web/news)                     tables: agents, decisions,
   Yahoo Finance MCP / Finnhub (data)      audit_entries, trust_scores,
     [fronted by MCP security gateway]      approvals, shadow_findings,
                                            mcp_scans
```

**Design rule:** React cannot call Python AGT libraries directly, so the FastAPI backend is the bridge. Governance enforcement happens **in-process** in the backend (the proven 🟢 REAL path); LangGraph handles flow; the React Governance page reads from the store the backend writes to.

**Governance guarantee:** every tool call is wrapped with AGT `govern()` directly (deterministic, in-process). LangGraph provides orchestration and the human-in-the-loop interrupt for approvals, but is NOT relied upon for the allow/deny guarantee.

---

## 3. Agents (6)

| # | Agent | Role | Must NOT | Execution ring |
|---|-------|------|----------|----------------|
| 1 | **Research** | Tavily web/news search; summarize market sentiment | spawn processes, write files | restricted: net = Tavily only |
| 2 | **Market-Data** | Fetch quotes/fundamentals via Yahoo Finance MCP + Finnhub | reach non-data hosts | restricted: net = data hosts only |
| 3 | **Strategy** | Synthesize research + data into a trade proposal | execute, approve | no network |
| 4 | **Risk Officer** | Enforce hard limits (max size, blocked instruments, exposure) | be bypassed | no network (deterministic) |
| 5 | **Execution** | Place trades below threshold (paper broker); above → require approval | place real orders; exceed limits | tightest: no fs, no subprocess |
| 6 | **Governance/Discovery** | Shadow-agent scan, trust aggregation, dashboard feed, kill switch | — | monitor-only |

Flow (LangGraph graph):
`Research → Market-Data → Strategy → Risk Officer → Execution → (approve? → human) → done`

Each node, before acting, passes through AGT `govern()`. A denied action short-circuits the graph and is logged.

---

## 4. External services (all free tier, no credit card)

| Service | Free tier | Env var | Role |
|---------|-----------|---------|------|
| **Groq** | OpenAI-compatible, generous per-minute, tool-calling on Llama | `GROQ_API_KEY` | Primary LLM |
| **Google Gemini** | ~1,500 req/day | `GEMINI_API_KEY` | Fallback LLM |
| **Tavily** | 1,000 credits/month (keyless mode exists) | `TAVILY_API_KEY` | Web/news research |
| **Finnhub** | real-time, ~60 calls/min | `FINNHUB_API_KEY` | Primary market data |
| **Yahoo Finance MCP** | no key, local process | — | Market-data **MCP tool** (what MCP security governs) |
| **Alpha Vantage** | 25 calls/day | `ALPHAVANTAGE_API_KEY` | Fallback data (low limit → drives rate-limit demo) |

Rules: **no secrets in code**, all via env vars / `.env` (gitignored). Market-data MCP runs as a **local** process (localhost-safe). Aggressive caching to respect free limits.

---

## 5. Feature → implementation map (every 🟢 REAL feature does real work)

| AGT feature | FEATURES.md row | Where in GovDesk |
|---|---|---|
| `govern()` + PolicyEngine | Policy | Every agent's tool calls wrapped |
| Policy DSL (numeric/compound/`in`) | Policy | `action.type=='trade' and action.amount>100000`; blocked instruments `in [...]` |
| Rate limiting (`PolicyRule.limit`) | Policy | Trades/hour cap; Alpha Vantage 25/day cap |
| `require_approval` | Policy | High-value trades → human (LangGraph interrupt) |
| Execution Rings | Runtime | Per-agent network/fs/subprocess scope |
| Command denylist | Runtime | Block shell/destructive ops from research agents |
| Kill Switch | Runtime | Governance page button halts an agent |
| MCP Security Scanner/Gateway/Response Scanner | MCP | Scan Yahoo/Finnhub MCP tool defs; sanitize responses |
| Shadow AI Discovery | Discovery | Governance agent scans for unregistered agents |
| Marketplace trust/quality + signing | Marketplace | MCP data-tools vetted + signed before use |
| Prompt injection + PromptDefenseEvaluator | Safety/Compliance | Research inputs scanned; prompts graded in CI |
| Advisory layer | Policy | Probabilistic classifier flags suspicious-but-allowed trades |
| AgentIdentity (DID) | Identity | Each of 6 agents signed |
| Trust scoring (RewardEngine) | Trust | Denied proposals lower score → auto-revoke |
| AuditLog + FileAuditSink | Audit | Every decision hash-chained + persisted |
| SLO / circuit breaker | SRE | Data-fetch SLOs; breaker on source failure |
| Compliance CLI (verify/integrity/lint-policy/test) | Compliance | CI gate + attestation |
| Cross-service dashboard | Serving | React Governance page over FastAPI + store |

---

## 6. The "Agent Governance" page (React centerpiece)

Sections:
1. **Agent roster** — card per agent: DID, trust score + tier, status (active/suspended/revoked), execution ring, capabilities.
2. **Decision timeline** — live (WebSocket) stream: timestamp · agent · action · verdict (allow/deny/require_approval) · matched rule · reason · latency. Filter by agent/verdict.
3. **Audit trail** — hash-chained entries + **Verify integrity** button (✓ when chain validates).
4. **Approvals queue** — pending high-value trades; approve/reject (writes back through the graph interrupt).
5. **Security panel** — MCP scan findings, prompt-defense grades, shadow-agent alerts.
6. **Trust charts** — score-over-time per agent; dimension breakdown.
7. **Kill switch** — halt a selected agent (confirmation dialog).

Supporting pages: **Desk** (run a research→proposal cycle), **Policies** (view/validate active YAML).

---

## 7. Folder layout

```
research_governance/
  plan.md                      ← this file
  README.md                    (added in build)
  .env.example
  backend/
    app/
      main.py                  FastAPI app + WebSocket
      graph/                   LangGraph agent graph + nodes
        desk_graph.py
        nodes/{research,market_data,strategy,risk,execution,governance}.py
      governance/              AGT wiring (in-process)
        gate.py                govern() wrappers per agent
        identities.py          AgentIdentity per agent
        audit.py               AuditLog + FileAuditSink
        trust.py               RewardEngine
        rings.py               RingEnforcer config per agent
        killswitch.py
        mcp_security.py        MCP scanner/gateway in front of data MCP
        discovery.py           shadow scan
        marketplace.py         MCP-tool vetting + signing
      policies/
        research.yaml  market_data.yaml  strategy.yaml
        risk.yaml      execution.yaml
      integrations/
        llm.py                 Groq + Gemini
        tavily_client.py
        market_mcp.py          Yahoo Finance MCP client
        finnhub_client.py
      store/
        db.py                  SQLite/Postgres
        models.py              agents, decisions, audit, trust, approvals, shadow, mcp_scans
      api/
        routes_desk.py  routes_governance.py  routes_approvals.py
    pyproject.toml / requirements.txt
    tests/
  frontend/
    (Vite + React)
    src/pages/{Desk,AgentGovernance,Policies}.tsx
    src/components/governance/{AgentRoster,DecisionTimeline,AuditTrail,ApprovalsQueue,SecurityPanel,TrustCharts,KillSwitch}.tsx
    src/lib/api.ts  src/lib/ws.ts
```

Lives under `research_governance/` (self-contained, outside AGT core packages).

---

## 8. Build phases

| Phase | Deliverable | Features landed |
|-------|-------------|-----------------|
| **1 — Core desk** | 4 agents (Research/Strategy/Risk/Execution), govern()+policies, identity, in-memory→SQLite audit, Tavily + one LLM, FastAPI + minimal React Governance page reading real data | Policy, identity, audit, require_approval, prompt-defense |
| **2 — MCP data + security** | Market-Data agent via Yahoo Finance MCP, MCP scanner/gateway in front, rate limiting | MCP security, rate limits |
| **3 — Runtime hardening** | Execution rings per agent, command denylist, kill switch, circuit breaker/SLO | Rings, denylist, kill switch, SRE |
| **4 — Trust + advisory** | RewardEngine scoring + auto-revoke, advisory classifier on trades, trust charts | Trust scoring, advisory |
| **5 — Platform plane** | Shadow discovery, marketplace vetting/signing, full Governance page, compliance CLI in CI | Discovery, marketplace, compliance |

Recommended start: **Phase 1–2**, with the React Governance page wired to real data from day one, then grow.

---

## 9. Tech stack

| Layer | Choice |
|-------|--------|
| Frontend | React (Vite) + TypeScript; WebSocket for live updates |
| Backend | FastAPI + Uvicorn |
| Orchestration | LangGraph (graph + approval interrupts) |
| Governance | AGT libraries in-process (local `agent-mesh/src` on path, as validated) |
| LLM | Groq (default) + Gemini fallback |
| Research | Tavily |
| Market data | Yahoo Finance MCP + Finnhub (+ Alpha Vantage fallback), behind MCP gateway |
| Store | SQLite (dev) → Postgres (later) |

---

## 10. Honest scoping / risks

- **Simulated broker only** — Execution logs "would place order"; no real brokerage. Stated in code + README.
- **Preview-grade features** (saga, chaos) used lightly and labeled, per FEATURES.md.
- **Free-tier limits are real** — Alpha Vantage 25/day is the fallback and is cached; this is a deliberate forcing function for the rate-limit feature.
- **LangGraph adapter** is 🟡 not-yet-validated here — we use LangGraph for orchestration and wrap tools with `govern()` directly for the enforcement guarantee, rather than depending on the adapter.
- **MCP servers run locally** — localhost-safe, documented in README.
- **No secrets in code** — env vars only; `.env` gitignored; `.env.example` provided.
- **Not financial advice** — disclaimer in UI and README.

---

## 11. Open questions to confirm before building

1. Scope: start at **Phase 1–2** (recommended) or spec/build the full 5 phases?
2. Backend package manager: `requirements.txt` (simplest) or `pyproject.toml`?
3. Any preference on React styling (plain CSS / Tailwind / a component lib)?
```
