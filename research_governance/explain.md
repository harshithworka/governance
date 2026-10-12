<!-- Copyright (c) Microsoft Corporation. Licensed under the MIT License. -->

# GovDesk — Complete Developer Guide (A → Z)

> **Who this is for:** a developer who has a high‑level idea of what the project
> is, but has not read the code. By the end of this document you should
> understand *everything*: what the project does, why it is built this way, how
> every agent works, how the React frontend talks to the FastAPI backend, how
> the real‑time pipeline streams, how governance is enforced, and how to run and
> extend it.
>
> Read it top to bottom once. Then use the section headers as a map when you
> open the code.

---

## Table of contents

1. [What is GovDesk?](#1-what-is-govdesk)
2. [The one big idea: deterministic governance](#2-the-one-big-idea-deterministic-governance)
3. [The 10,000‑foot architecture](#3-the-10000-foot-architecture)
4. [The tech stack (and why each piece exists)](#4-the-tech-stack-and-why-each-piece-exists)
5. [Folder layout — where everything lives](#5-folder-layout--where-everything-lives)
6. [The backend, explained](#6-the-backend-explained)
7. [The 6 agents — what each does and how](#7-the-6-agents--what-each-does-and-how)
8. [The governance gate — the heart of the system](#8-the-governance-gate--the-heart-of-the-system)
9. [JEV — the per‑agent safety judge](#9-jev--the-per-agent-safety-judge)
10. [The real‑time pipeline (SSE streaming)](#10-the-real-time-pipeline-sse-streaming)
11. [How the frontend connects to the backend (the web‑dev part)](#11-how-the-frontend-connects-to-the-backend-the-web-dev-part)
12. [The frontend, page by page](#12-the-frontend-page-by-page)
13. [The database](#13-the-database)
14. [A full request, traced end to end](#14-a-full-request-traced-end-to-end)
15. [The demo controls (how the live demo works)](#15-the-demo-controls-how-the-live-demo-works)
16. [Configuration & environment variables](#16-configuration--environment-variables)
17. [How to run it locally](#17-how-to-run-it-locally)
18. [How to extend it](#18-how-to-extend-it)
19. [Honest limitations](#19-honest-limitations)
20. [Glossary](#20-glossary)
21. [Complete codebase reading order (every file)](#21-complete-codebase-reading-order-every-file)

> **How to use this doc to learn the code:** each section below ends with a
> **📖 Files to read** box listing the exact files for that topic, in order. If
> you want one single front-to-back path through the *entire* codebase, jump to
> **§21 — Complete codebase reading order** and follow it top to bottom; the
> per-section boxes then serve as the "why" for each file you open.

---

## 1. What is GovDesk?

GovDesk is a **demonstration** of a *governed* multi‑agent system, framed as a
"financial research desk." A user types a plain‑English request (e.g. *"Do a
complete analysis of HDFC Bank"*). Behind the scenes, **six AI agents** work in
a pipeline to research the company, pull market data, draft a trade thesis,
check it against risk limits, and (simulate) placing a trade.

The point of the project is **not** the trading. The point is that **every
single action an agent takes is governed before it runs** — checked against a
policy, attributed to a cryptographic identity, recorded in a tamper‑proof
audit log, scored for trust, and (new) re‑checked by a separate "JEV" safety
judge. It is built on Microsoft's open‑source **Agent Governance Toolkit (AGT)**.

> **It is a demo, not a trading system.** The only simulated piece is the final
> trade *placement* — a "paper" order. Everything else (news, prices, the LLM
> reasoning, the safety checks) is real.

---

## 2. The one big idea: deterministic governance

This is the single most important concept. Internalize it first.

- **LLM guardrails are *probabilistic*.** "Ask the model nicely not to do X," or
  "use a second model to judge the output." These work *most* of the time and
  fail silently the rest. You can never *guarantee* a bad action won't happen.
- **AGT governance is *deterministic*.** Before an action runs, plain Python
  code evaluates a policy rule and returns **allow / deny / require_approval**. A
  denied action isn't "unlikely" — it is *structurally impossible*, because the
  check happens in ordinary code *before* the action executes.

GovDesk uses **both**, in the correct order:

1. The **deterministic policy engine** makes the hard allow/deny decision.
2. On top, **probabilistic** layers (the advisory classifier, and now the **JEV
   safety judge**) can only *tighten* an already‑allowed action — never loosen a
   deny.

Whenever you see a "gate" or a "check" in this codebase, ask: *is this the
deterministic guarantee, or an advisory layer on top?* The deterministic policy
engine is the guarantee; everything else wraps around it.

---

## 3. The 10,000‑foot architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (research_governance/frontend)      React + Vite + TypeScript    │
│                                                                             │
│   • Desk page         — enter a query; watch the real-time agent pipeline   │
│   • Agent Governance  — the live dashboard (roster, decisions, audit, …)    │
│   • Policies page     — the active rules + demo threat-injection controls   │
└───────────────┬──────────────────────────────┬──────────────┬──────────────┘
                │ REST (fetch)                  │ SSE          │ WebSocket
                │ GET/POST JSON                 │ (pipeline)   │ (live decisions)
                ▼                               ▼              ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  BACKEND  (research_governance/backend)        FastAPI + Uvicorn            │
│                                                                             │
│   Agents run as a sequence of nodes. Each node calls the GOVERNANCE GATE    │
│   before acting. The gate uses the AGT libraries IN-PROCESS:                │
│     • PolicyEngine   (deterministic allow/deny)                             │
│     • AgentIdentity  (who did it — Ed25519 DIDs)                            │
│     • AuditLog       (tamper-evident hash chain)                            │
│     • RewardEngine   (trust scores)                                         │
│     • MCPSecurityScanner, RingEnforcer, KillSwitch, CircuitBreaker,         │
│       advisory, discovery, marketplace, intake, JEV                         │
└───────────────┬──────────────────────────────────────────┬─────────────────┘
                │                                            │  external APIs
                ▼                                            ▼  ───────────────
         SQLite  (govdesk.db)                        Tavily  (news)
         agents, decisions, audit_entries,           Finnhub (quotes)
         trust_scores, approvals, mcp_scans,          Groq    (LLM + JEV judge)
         runtime_events, shadow_agents,               (Gemini optional)
         plugin_vettings, intake_events, rag_...      OpenRouter (optional JEV)
```

Two things to burn into memory:

1. **The frontend cannot call Python.** React talks to the backend over HTTP
   (REST), a WebSocket (live decision feed), and SSE (the pipeline stream). The
   governance guarantee lives entirely in the **backend**, in Python, in the
   same process ("in‑process").
2. **The backend resets its database on every startup.** Agent identities are
   minted fresh each run, so the dashboard always reflects the *current*
   process. (Durable history across restarts would need stable identities — a
   deliberate simplification for a demo.)

---

## 4. The tech stack (and why each piece exists)

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | **React + Vite + TypeScript** | Fast dev server, typed UI, component model |
| Styling | **Plain CSS** (one `styles.css`, CSS variables) | No build complexity, no Tailwind dependency |
| Backend | **FastAPI + Uvicorn** | Async Python web framework; auto OpenAPI docs at `/docs` |
| Governance | **AGT libraries, in‑process** | The deterministic enforcement runs as library calls, not a network hop |
| Agents | Plain Python functions ("nodes") run in sequence | Simple, debuggable; each node calls the gate then does its work |
| Store | **SQLite** (`govdesk.db`) | Zero‑setup embedded DB the dashboard reads from |
| LLM | **Groq** (primary), Gemini (optional fallback) | Free, fast, OpenAI‑compatible |
| Research | **Tavily** | Live web/news search |
| Market data | **Finnhub** | Live quotes |
| Safety judge (JEV) | **OpenRouter** (primary) → **Groq** (fallback) | A real LLM scoring each agent's output 0–1 |
| RAG | **ChromaDB + Gemini embeddings** | Grounds analysis in annual‑report PDFs |

> **"In‑process" matters.** Because governance is a Python library call inside
> the backend (not a separate service it calls over the network), there is no
> way for an agent to "skip" the check. The check *is* the code path.

---

## 5. Folder layout — where everything lives

```
research_governance/
├── README.md                 ← quick start + feature summary
├── plan.md                   ← original design doc
├── explain.md                ← THIS FILE
│
├── backend/                  ← the FastAPI app (Python)
│   ├── requirements.txt
│   ├── .env                  ← API keys (gitignored, you create it)
│   └── app/
│       ├── main.py           ← FastAPI app factory + WebSocket + SSE wiring
│       ├── config.py         ← settings + AGT import bootstrap (reads .env)
│       │
│       ├── api/              ← HTTP route handlers (the "controllers")
│       │   ├── routes_desk.py        ← /api/desk/* (intake, run, run-stream)
│       │   ├── routes_governance.py  ← /api/governance/* (the dashboard data)
│       │   └── routes_approvals.py   ← /api/approvals/* (human approval queue)
│       │
│       ├── graph/            ← the agent pipeline
│       │   ├── state.py           ← DeskState: data passed between agents
│       │   ├── desk_graph.py      ← the 5 agent "nodes" + run_desk()
│       │   └── desk_stream.py     ← sequential, event-emitting run (SSE)
│       │
│       ├── governance/      ← ALL the AGT wiring (the important folder)
│       │   ├── gate.py            ← THE HEART. GovernanceGate.evaluate()
│       │   ├── identities.py      ← the 6 agents + their Ed25519 DIDs
│       │   ├── jev.py             ← the per-agent safety judge (NEW)
│       │   ├── advisory.py        ← probabilistic trade-risk classifier
│       │   ├── mcp_security.py    ← scans MCP tools for poisoning/typosquats
│       │   ├── rings.py           ← execution rings + command denylist
│       │   ├── killswitch.py      ← terminate an agent
│       │   ├── reliability.py     ← circuit breakers + SLO counters
│       │   ├── discovery.py       ← shadow-AI discovery
│       │   ├── marketplace.py     ← MCP-tool vetting + signing
│       │   ├── intake.py          ← PII redaction + injection scan + symbol
│       │   └── demo_controls.py   ← presenter demo: inject threats + reset
│       │
│       ├── integrations/    ← external providers
│       │   ├── providers.py       ← research (Tavily), market (Finnhub), LLM (Groq)
│       │   └── rag.py             ← annual-report RAG (ChromaDB + Gemini)
│       │
│       ├── mcp/
│       │   └── catalog.py         ← MCP tool definitions (incl. demo-malicious)
│       │
│       ├── policies/        ← one YAML policy per agent
│       │   ├── research.yaml  market_data.yaml  strategy.yaml
│       │   ├── risk.yaml      execution.yaml
│       │
│       └── store/
│           └── db.py              ← SQLite: schema + all read/write functions
│
└── frontend/                 ← the React app (TypeScript)
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx          ← React entry point
        ├── App.tsx           ← sidebar + routes (the shell)
        ├── styles.css        ← the ENTIRE theme (CSS variables + classes)
        │
        ├── lib/              ← the glue to the backend
        │   ├── api.ts             ← every REST call, one object `api`
        │   ├── ws.ts              ← WebSocket helper (live decisions)
        │   ├── pipeline.ts        ← SSE helper (the agent pipeline stream)
        │   └── types.ts           ← TypeScript types mirroring backend JSON
        │
        ├── pages/            ← one component per route
        │   ├── Desk.tsx           ← query + real-time pipeline (the main page)
        │   ├── AgentGovernance.tsx← the dashboard (composes all panels)
        │   └── Policies.tsx       ← rules + demo controls
        │
        └── components/       ← the dashboard panels
            ├── AgentRoster.tsx  DecisionTimeline.tsx  AuditTrail.tsx
            ├── ApprovalsQueue.tsx  SecurityPanel.tsx  RuntimePanel.tsx
            ├── AdvisoryPanel.tsx  ShadowDiscoveryPanel.tsx
            └── MarketplacePanel.tsx  IntakePanel.tsx  RagPanel.tsx
```

---

## 6. The backend, explained

The backend is a standard FastAPI app. The lifecycle:

1. **`config.py` runs first (on import).** It does two jobs:
   - **AGT import bootstrap.** The AGT libraries live elsewhere in the monorepo.
     `config.py` adds their `src` folders to Python's `sys.path` so
     `import agentmesh`, `import agent_os`, `import hypervisor`, etc. work. This
     is *why* those imports resolve.
   - **Settings.** It reads `.env` (via `python-dotenv`) into a frozen
     `Settings` dataclass — API keys, model names, ports, CORS origins. Helper
     properties like `has_llm`, `has_jev` tell the rest of the app which live
     providers are available.

2. **`main.py` creates the FastAPI app** (`create_app()`):
   - Adds **CORS** middleware (so the browser on `:5173` may call the API on
     `:8099`).
   - Registers the three routers (`routes_desk`, `routes_governance`,
     `routes_approvals`).
   - On **startup**: initializes + resets the DB, mints agent identities, runs
     the first MCP scan / marketplace vet / discovery scan so the dashboard has
     data, and wires the **live decision WebSocket** (see §11).
   - Exposes `/api/health` (returns `{status, mode}`) and `/ws/decisions`.

3. **Routes receive HTTP requests, call into `graph/` and `governance/`, and
   return JSON.** Routes are thin; the real logic is in the agent nodes and the
   gate.

**Mental model:** `api/` = controllers, `graph/` = the agent workflow,
`governance/` = the rules engine, `integrations/` = the outside world,
`store/` = the database.

> **📖 Files to read for this section, in order:**
> 1. `backend/app/config.py` — the AGT import bootstrap + `Settings` dataclass. Read this first; it is *why* every `import agentmesh` / `import agent_os` works.
> 2. `backend/app/main.py` — the FastAPI app factory, CORS, router registration, startup hooks, the WebSocket (`/ws/decisions`), and the SSE fan-out wiring.
> 3. `backend/app/store/db.py` — skim the schema near the top; it names every table the dashboard reads. You'll return here often.
> 4. `backend/app/__init__.py` — trivial, just marks the package.

---

## 7. The 6 agents — what each does and how

The agents are **plain Python functions** called "nodes," defined in
`graph/desk_graph.py`. They run in a fixed order. Each one:

1. Calls the **governance gate** (`gate.evaluate(...)`) *first*.
2. If allowed, does its real work (calls a provider / the LLM).
3. Writes its result into the shared **`DeskState`** dict (`graph/state.py`),
   which is threaded through all the nodes.

> An "agent" here is **not** an autonomous LLM loop. It is a governed step that
> may call an LLM or an API. This keeps the demo deterministic and debuggable.
> The agents' *identities* (DIDs, trust, rings) are what make them "agents" in
> the governance sense.

| # | Agent | What it does | How it gets data | Governed by |
|---|-------|--------------|------------------|-------------|
| 1 | **Research** | Gathers news + sentiment | **Tavily** live search (mock headlines if no key) | policy (web search allowed, writes/trades denied); **RING_2** (network allowed); **circuit breaker** |
| 2 | **Market‑Data** | Fetches live price **and** annual‑report fundamentals | **Finnhub** quote + **RAG** over the NSE annual‑report PDF | policy; **MCP tool security** (only a scanned‑safe tool may be used); RING_2; retrieved chunks are **injection‑screened** |
| 3 | **Strategy** | Writes a one‑line trade thesis | the **LLM** (Groq → Gemini fallback) | policy (may draft, never execute/approve); **RING_3 sandbox** (no network) |
| 4 | **Risk Officer** | Checks the proposal against hard limits | nothing external — pure deterministic logic | policy with **numeric + list rules** (block > ₹250k, block instruments on a blocklist) |
| 5 | **Execution** | Places the (paper) trade | nothing external | the richest policy: small trades allowed, **≥ ₹100k → require human approval**, destructive ops denied; tightest sandbox; **advisory layer**; rate limit; **kill switch** target |
| 6 | **Governance / Discovery** | Background oversight — hunts "shadow" agents, aggregates data | — | it *is* the governance plane; runs the shadow‑discovery scan |

Only agents 1–5 execute in the pipeline. Agent 6 is monitor‑only.

> **📖 Files to read for this section, in order:**
> 1. `backend/app/graph/state.py` — `DeskState`, the dict threaded through all agents. Small; read it first so the node code makes sense.
> 2. `backend/app/graph/desk_graph.py` — the 5 agent **node functions** (`research_node` … `execution_node`) and `run_desk()`. This is where each agent calls the gate, the ring check, the breaker, then does its work. The single most important agent file.
> 3. `backend/app/governance/identities.py` — the 6 agents, their rings/capabilities, and their Ed25519 DIDs (`AgentIdentity.create`).
> 4. `backend/app/integrations/providers.py` — the real provider calls each agent makes: `research_headlines` (Tavily), `market_quote` (Finnhub), `llm_summarize` (Groq→Gemini), with mock fallbacks.
> 5. `backend/app/integrations/rag.py` — the Market-Data agent's second tool: the NSE annual-report RAG pipeline (fetch → pypdf → chunk → embed → ChromaDB → retrieve).
> 6. `backend/app/mcp/catalog.py` — the MCP tool definitions the Market-Data agent chooses from (including the demo-malicious ones).

**Each agent node also runs through two more gates (phases 2–3):**
- A **ring check** (`rings.check_resource(...)`) — may this agent touch the
  network at all? Research/Market‑Data are RING_2 (yes); Strategy/Risk/Execution
  are RING_3 sandbox (no).
- A **circuit breaker** (`reliability.call(...)`) wraps the live provider call —
  if a provider keeps failing, the breaker trips OPEN and blocks further calls
  instead of hanging.

---

## 8. The governance gate — the heart of the system

**The single most important file is `backend/app/governance/gate.py`.** Every
agent action flows through `GovernanceGate.evaluate(agent_key, action, ...)`.
Read that method slowly; everything else feeds into or reads from it.

What one call to `evaluate()` does, in order:

1. **Policy evaluation (deterministic).** Loads the agent's YAML policy into an
   AGT `PolicyEngine` and calls `engine.evaluate(did, {"action": {...}})`. Gets
   back **allow / deny / require_approval** plus the matched rule.
2. **Advisory layer (probabilistic, only after an `allow`).** For trades, a
   heuristic classifier (`advisory.py`) can *flag* (still allowed) or *block*
   (downgrade the allow to a deny). It can **never** turn a deny into an allow.
3. **Audit.** Writes a hash‑chained entry into the AGT `AuditLog` and persists
   it to SQLite. Each entry links to the previous one by hash → tamper‑evident.
4. **Trust.** Feeds a "compliance signal" (allow = 1.0, deny = 0.0, …) into the
   AGT `RewardEngine`, recomputes the agent's 0–1000 trust score, and
   **auto‑suspends** the agent if it drops below 250.
5. **Persist + broadcast.** Writes the decision row to SQLite and **broadcasts**
   it to any live WebSocket listeners (so the dashboard's Decision Timeline
   updates in real time).

The return value is a `Verdict` object the agent node reads: `allowed`,
`verdict`, `requires_approval`, `reason`, etc. The node uses that to decide
whether to proceed, stop, or route to human approval.

> **📖 Files to read for this section, in order (this is the heart of the project):**
> 1. `backend/app/governance/gate.py` — **read `GovernanceGate.evaluate()` slowly.** Everything (policy, advisory, audit, trust, broadcast) ties together here.
> 2. `backend/app/policies/execution.yaml` — the richest policy (numeric + compound conditions + `require_approval` + rate limit). Read this first of the policies.
> 3. `backend/app/policies/risk.yaml` — numeric limit + instrument blocklist (the clearest deterministic deny).
> 4. `backend/app/policies/research.yaml`, `market_data.yaml`, `strategy.yaml` — the simpler per-agent policies.
> 5. `backend/app/governance/advisory.py` — the probabilistic trade-risk classifier that runs *after* a deterministic allow and can only tighten it.
> 6. (AGT library, optional deep dive) `agent-governance-python/agent-mesh/src/agentmesh/governance/policy.py` — the `PolicyEngine` condition parser + conflict resolution, if you want to see how a YAML `condition` string is actually evaluated.

---

## 9. JEV — the per‑agent safety judge

**JEV** (`backend/app/governance/jev.py`) is an **additional** safety layer that
runs **after each agent produces its output**, independent of the policy gate.

- It takes the agent's real output text and asks a **real LLM** to judge it:
  *is this output good — no foul language, no harmful content, no sensitive
  content?* The model returns a **safety score between 0 and 1** (higher =
  safer) plus a short reason, as strict JSON.
- **Threshold = 0.5.** `safe = score >= 0.5`. A live score **below 0.5 blocks
  the pipeline** — the next agent never starts, and the UI marks that agent red.
- JEV is a *tightening* layer, like the advisory: it can stop a flow, but the
  deterministic policy gate is still the primary guarantee.

**Which model does JEV use? (resolution order):**
1. If `JEV_API_KEY` is set → **OpenRouter** (a dedicated judge model, config
   `JEV_MODEL`, default `openai/gpt-4o-mini`). This is the intended production
   path with its own quota.
2. Else if `GROQ_MODEL_2` is set → **Groq fallback** (a *second* Groq API key,
   kept separate from the Strategy agent's key so JEV has its own rate‑limit
   budget; model `GROQ_JEV_MODEL`, default `openai/gpt-oss-20b`).
3. Else → **"unavailable"** — JEV returns no score, is shown honestly in the UI
   as "JEV unavailable," and is **non‑blocking** (so the demo still runs). We
   **never fabricate** a score.

On any network/parse error, JEV returns `source="error"` (also non‑blocking,
shown honestly). **Only a real live score < 0.5 blocks a run.**

> Design note: the agent's output is summarized into readable text in
> `desk_stream.py` (`_summarize`) and *that* text is what JEV judges — so the
> safety check is on the actual thing the agent produced.

> **📖 Files to read for this section, in order:**
> 1. `backend/app/governance/jev.py` — the whole JEV layer: `evaluate()` (resolution order), `_evaluate_openrouter()` (the **Jev Decisions API** call with a `noul` question), `_evaluate_groq()` (the chat-style fallback), and the threshold logic.
> 2. `backend/app/config.py` — re-read the JEV settings block (`jev_api_key`, `jev_model`, `groq_jev_api_key`, `groq_jev_model`, `has_jev`).
> 3. `backend/app/graph/desk_stream.py` — see `_summarize()` (builds the text JEV judges) and where `jev.evaluate()` is called between agents.

---

## 10. The real‑time pipeline (SSE streaming)

The Desk page shows the agents executing **one at a time, live**: each agent
glows green while running, shows its output, then its JEV score, before the next
agent starts. This is driven by **Server‑Sent Events (SSE)**, not a fake
animation.

**Backend side — `graph/desk_stream.py` + the `/api/desk/run-stream` route:**

- `run_desk_events(symbol, amount, query)` is a **generator** that runs the same
  5 agent nodes **one at a time** and `yield`s event dicts in strict order:

  ```
  WORKFLOW_STARTED
  for each agent:
      AGENT_STARTED            → UI: this agent turns green/running
      AGENT_COMPLETED (output) → UI: show the output card
      JEV_STARTED              → UI: "JEV: Evaluating…"
      JEV_COMPLETED (score)    → UI: show Safe/Unsafe + probability bar
      [if JEV < 0.5 or policy block: AGENT_BLOCKED + WORKFLOW_BLOCKED → stop]
  WORKFLOW_COMPLETED           (only if every agent passed)
  ```

- The route (`run_stream` in `routes_desk.py`) runs that **blocking** generator
  in a **worker thread** and pumps each event onto an `asyncio.Queue`, then
  streams them to the browser as `data: {json}\n\n` SSE frames. Running the work
  in a thread is what makes the stream *progressive* (one event at a time)
  rather than all‑at‑once.

**Why SSE and not the WebSocket?** SSE is a one‑way, GET‑only, auto‑framed stream
— perfect for "server pushes an ordered sequence of events for one run." The
WebSocket (`/ws/decisions`) is a separate, always‑on feed of *every* governance
decision for the dashboard. They serve different purposes.

**The human‑approval case:** if a trade is ≥ ₹100k, the Execution agent returns
`require_approval`. The stream emits `WORKFLOW_BLOCKED` with `stage="approval"`
and an `approval_id`, then ends. The Desk page then **polls** the approvals
endpoint; when a human approves/rejects it on the Governance page, the Desk page
updates the Execution node accordingly. (This is why the pipeline can "resume"
visually after you approve.)

> **📖 Files to read for this section, in order:**
> 1. `backend/app/graph/desk_stream.py` — `run_desk_events()`: the generator that runs agents one at a time and `yield`s the ordered events. Read the event schema in its docstring.
> 2. `backend/app/api/routes_desk.py` — the `run_stream` route: how the blocking generator is pumped onto an `asyncio.Queue` in a worker thread and streamed as SSE (`text/event-stream`). Also `intake` and `run` routes here.
> 3. `backend/app/api/routes_approvals.py` — the human-approval queue + `resume_after_approval`.
> 4. `backend/app/api/__init__.py` — trivial package marker.

---

## 11. How the frontend connects to the backend (the web‑dev part)

This is the section a web developer most wants. There are **three** channels.

### Channel 1 — REST (request/response), via `lib/api.ts`

Every call to the backend goes through one object, `api`, in
`frontend/src/lib/api.ts`. It has two tiny helpers:

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8099";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
```

Then `api` is just a dictionary of typed functions, e.g.:

```ts
export const api = {
  base: BASE,
  intake:   (query) => post<IntakeResult>("/api/desk/intake", { query }),
  agents:   () => get<{ items: Agent[] }>("/api/governance/agents"),
  mcpRescan:() => post("/api/governance/mcp/scan"),
  resolveApproval: (id, approved) => post(`/api/approvals/${id}/resolve`, { approved }),
  // …one function per endpoint
};
```

A React component just calls `api.agents()` and gets back typed data. **All URLs
and request shapes live in this one file** — if the backend changes, you update
`api.ts` and `types.ts` and nothing else.

**The CORS link:** the browser (origin `http://localhost:5173`) is calling a
different origin (`http://127.0.0.1:8099`). The backend's CORS middleware
(configured in `main.py` from `GOVDESK_CORS_ORIGINS`) explicitly allows that
origin, which is what makes the cross‑origin `fetch` succeed.

### Channel 2 — WebSocket (live decision feed), via `lib/ws.ts`

The dashboard's **Decision Timeline** needs to update the instant any agent is
governed. Polling would be laggy, so we use a WebSocket:

- Backend: `/ws/decisions`. When the gate decides anything, `gate._broadcast()`
  puts the decision on an asyncio queue, and a fan‑out task `send_json`s it to
  every connected socket.
- Frontend: `connectDecisions(onEvent)` in `ws.ts` opens
  `ws://127.0.0.1:8099/ws/decisions`, parses each JSON message, and calls your
  handler. It **auto‑reconnects** if the socket drops. It returns a `close()`
  function the component calls on unmount.

```ts
const close = connectDecisions((payload) => {
  if (payload.kind === "decision") addRow(payload);
});
// later, on unmount:  close();
```

### Channel 3 — SSE (the agent pipeline), via `lib/pipeline.ts`

For the Desk page's live pipeline (see §10), we use the browser's native
`EventSource`:

```ts
export function connectPipeline(params, onEvent, onError) {
  const url = `${api.base}/api/desk/run-stream?symbol=...&amount=...&query=...`;
  const es = new EventSource(url);               // GET-only → params in query string
  es.onmessage = (ev) => {
    const event = JSON.parse(ev.data);           // a PipelineEvent
    onEvent(event);
    if (event.type === "WORKFLOW_COMPLETED" || event.type === "WORKFLOW_BLOCKED")
      es.close();                                // one-shot run; stop at the end
  };
  es.onerror = (err) => { onError?.(err); es.close(); };
  return () => es.close();                        // caller closes on unmount
}
```

The Desk page feeds every event into a **reducer** (`useReducer`) keyed by agent
index, which updates the on‑screen pipeline state. That reducer is why the UI
reflects *exactly* the real backend events and never pre‑reveals an agent.

### Type safety across the wire

`frontend/src/lib/types.ts` declares TypeScript interfaces that **mirror the
JSON** the backend returns (`Agent`, `Decision`, `AuditEntry`, `PipelineEvent`,
`IntakeResult`, …). This isn't enforced at runtime, but it means the compiler
catches mismatches, and a developer reading `types.ts` can see every data shape
the frontend expects.

> **📖 Files to read for this section, in order (the frontend↔backend glue):**
> 1. `frontend/src/lib/types.ts` — every data shape the frontend expects. Read first; the rest references these types.
> 2. `frontend/src/lib/api.ts` — the `get`/`post` helpers (native `fetch`) and the `api` object: one typed function per REST endpoint. This is the entire REST contract.
> 3. `frontend/src/lib/ws.ts` — `connectDecisions()`: the WebSocket helper for the live decision feed (with auto-reconnect).
> 4. `frontend/src/lib/pipeline.ts` — `connectPipeline()`: the SSE (`EventSource`) helper for the real-time agent pipeline.
> 5. `frontend/src/main.tsx` — the React entry point (mounts `<App/>`).
> 6. `frontend/src/vite-env.d.ts` — Vite type shim (trivial).

---

## 12. The frontend, page by page

The shell is `App.tsx`: a left **sidebar** (brand + nav + backend‑mode badge)
and a routed **main area** using `react-router-dom`. Three routes:

### Desk page (`pages/Desk.tsx`) — the main attraction

- **Top:** a query box + amount + example buttons. Clicking **Run intake** calls
  `api.intake(query)`, which returns the governed‑intake result: PII redactions,
  the injection scan verdict, the resolved NSE symbol, and the prompt‑defense
  grade. Shown in the "Intake result" panel.
- **Run Workflow:** opens the SSE pipeline (`connectPipeline`). The page then
  shows **two columns**:
  - **Left:** the 6 agents as a vertical connected pipeline. Each node has a
    state — idle (grey), running (green glow + spinner), done (green check),
    blocked (red), waiting (muted). Only one runs at a time.
  - **Right:** "Agent Outputs & JEV Results" — one card per agent appears in
    execution order, each showing the agent's output and, inside the same card,
    the JEV result (Safe/Unsafe badge, probability, score bar).
- **Persistence:** the last run (query, intake, and the pipeline result) is
  saved to `localStorage` so navigating away and back — or refreshing — re‑shows
  it. A run interrupted mid‑stream is restored as a settled snapshot (no frozen
  spinner).

### Agent Governance page (`pages/AgentGovernance.tsx`) — the dashboard

Composes all the panels in `components/`. Each panel calls its own `api.*`
function (and some refresh on a timer). Panels:

- **Agent Roster** — card per agent: DID, trust bar + tier, status, ring,
  capabilities, and a **Kill** button.
- **Decision Timeline** — live (WebSocket) stream of every allow/deny.
- **Approvals Queue** — pending high‑value trades; Approve/Reject.
- **Audit Trail** — hash‑chained entries + a **Verify integrity** button.
- **MCP Tool Security** — per‑tool scan verdicts + Re‑scan.
- **Runtime Hardening** — rings, circuit breakers, kill history, "Simulate
  egress attempt."
- **Advisory**, **Shadow Discovery**, **Marketplace Vetting**, **Governed
  Intake**, **Annual‑report RAG** — one panel each.

### Policies page (`pages/Policies.tsx`)

A summary of each agent's active rules, plus the **Demo controls** panel (§15).

> **📖 Files to read for this section, in order:**
> 1. `frontend/src/App.tsx` — the shell: sidebar, nav, backend-mode badge, and the `react-router-dom` routes. Start here.
> 2. `frontend/src/styles.css` — the entire theme (CSS variables + every class). Skim it so the components' class names make sense.
> 3. `frontend/src/pages/Desk.tsx` — the main page: query → intake → the live SSE pipeline (reducer + the two-column UI + persistence + approval polling). The biggest frontend file; read it carefully.
> 4. `frontend/src/pages/AgentGovernance.tsx` — composes all the dashboard panels + the 4 KPI cards.
> 5. `frontend/src/pages/Policies.tsx` — the rules table + demo-controls buttons.
> 6. Then the panels in `frontend/src/components/`, each paired with the backend endpoint it reads (via `api.*`):
>    - `AgentRoster.tsx` → `api.agents` / `api.kill` / `api.reactivate`
>    - `DecisionTimeline.tsx` → `api.decisions` + the WebSocket (`ws.ts`)
>    - `ApprovalsQueue.tsx` → `api.approvals` / `api.resolveApproval`
>    - `AuditTrail.tsx` → `api.audit` / `api.verifyAudit`
>    - `SecurityPanel.tsx` → `api.mcpScans` / `api.mcpRescan`
>    - `RuntimePanel.tsx` → `api.rings` / `api.breakers` / `api.runtimeEvents` / `api.egressTest`
>    - `AdvisoryPanel.tsx` → `api.advisory`
>    - `ShadowDiscoveryPanel.tsx` → `api.shadows` / `api.discoveryScan`
>    - `MarketplacePanel.tsx` → `api.marketplace` / `api.marketplaceVet`
>    - `IntakePanel.tsx` → `api.intakeEventsList`
>    - `RagPanel.tsx` → `api.ragRetrievals`

---

## 13. The database

`backend/app/store/db.py` is a thin wrapper over SQLite (`govdesk.db`). It
defines the schema (one table per record type) and all read/write functions.
Key tables:

| Table | Holds |
|-------|-------|
| `agents` | the 6 agents: DID, name, ring, trust score/tier, status |
| `decisions` | every governed decision (what the Decision Timeline shows) |
| `audit_entries` | the hash‑chained audit log entries |
| `trust_scores` | trust‑score history points per agent |
| `approvals` | the human‑approval queue |
| `mcp_scans` | MCP tool security verdicts |
| `runtime_events` | ring denials, breaker trips, kills, RAG‑injection blocks |
| `shadow_agents` | discovered agents + shadow/registered status + risk |
| `plugin_vettings` | marketplace vetting results per tool |
| `intake_events` | governed‑intake events (PII, injection, symbol) |
| `rag_retrievals` | annual‑report RAG retrievals |

> **The DB resets on every startup** (`db.reset_db()` is called in
> `gate.setup()`), because agent identities are minted fresh per process. The
> dashboard always reflects the current run.

> **📖 Files to read for this section:**
> 1. `backend/app/store/db.py` — the whole store: the `_SCHEMA` string (every table), plus one pair of read/write functions per record type. There is no ORM; it's plain SQLite via `sqlite3`.
> 2. `backend/app/store/__init__.py` — trivial package marker.

---

## 14. A full request, traced end to end

Say the user types *"Do a complete analysis of HDFC Bank"* and runs the workflow
with amount ₹500.

1. **Browser → `POST /api/desk/intake`** (`api.intake`). Backend `intake.py`:
   redacts PII, scans for prompt injection (blocks if detected), grades the text
   with the prompt‑defense evaluator, and resolves "HDFC Bank" → `HDFCBANK` via
   the NSE master. Returns the intake result → shown in the UI.
2. User clicks **Run Workflow** → browser opens **`GET /api/desk/run-stream?
   symbol=HDFCBANK&amount=500&query=…`** (`connectPipeline` / `EventSource`).
3. Backend `run_desk_events` emits `WORKFLOW_STARTED`, then for each agent:
   - `AGENT_STARTED` → the node calls `gate.evaluate(...)` (policy + ring +
     breaker), then does its work (e.g. Research calls Tavily).
   - `AGENT_COMPLETED` with the output summary.
   - `JEV_STARTED` → `jev.evaluate(agent, output)` calls the judge LLM.
   - `JEV_COMPLETED` with the 0–1 score.
   - Every `gate.evaluate` also writes an audit entry, updates trust, and
     **broadcasts** the decision over the WebSocket → the dashboard's Decision
     Timeline updates live *at the same time*.
4. For ₹500 (small), the Execution agent is allowed → a **simulated** paper
   order. The stream ends with `WORKFLOW_COMPLETED`.
5. If the amount were ₹150,000, Execution would return `require_approval` →
   `WORKFLOW_BLOCKED (stage=approval)` → the Desk page polls approvals; a human
   approves on the Governance page; the Desk page updates Execution to "done."

Every step you just saw was policy‑checked, identity‑stamped, audited,
trust‑scored, and JEV‑judged — in real time.

---

## 15. The demo controls (how the live demo works)

The Policies page has a **Demo controls** panel for presentations. The important
property: **the controls only *plant* a threat; detection comes from the real
scanners when you click the existing re‑scan buttons.**

| Button | Effect | Then show on Agent Governance |
|--------|--------|-------------------------------|
| **Add risky MCP tool** | appends a poisoned tool to the catalog (undetected) | MCP tool security → **Re‑scan** → it's **blocked (critical)**; Marketplace → **Re‑vet** → **revoked** |
| **Add harmful agent** | plants a rogue, ownerless agent (undetected) | Shadow AI discovery → **Re‑scan** → it's **shadow / critical** |
| **Tamper with audit log** | corrupts one in‑memory audit entry | Audit trail → **Verify integrity** → flips to **FAILED** |
| **Reset demo threats** | clears injected items + repairs the chain | everything back to the clean baseline |

Backend: `governance/demo_controls.py` + the `/api/governance/demo/*` routes.
The injected items flow into the *same* real scan/vet/verify code paths — so the
governance genuinely catches them.

> **📖 Files to read for the demo controls + the governance modules they exercise, in order:**
> 1. `backend/app/governance/demo_controls.py` — plants a poisoned tool / rogue agent / tampers the audit chain, and resets. Shows how each threat is injected into the real scan paths.
> 2. `backend/app/governance/mcp_security.py` — `MCPSecurityScanner` wrapper: `scan_catalog()` + `is_tool_allowed()` (what blocks the poisoned tool).
> 3. `backend/app/governance/marketplace.py` — vets each tool as a signed plugin; forces a scan-blocked tool to `revoked`.
> 4. `backend/app/governance/discovery.py` — shadow-AI discovery: observes agents, reconciles against the registry, risk-scores shadows.
> 5. `backend/app/governance/rings.py` — execution rings + command denylist (`check_resource`, `check_command`).
> 6. `backend/app/governance/killswitch.py` — terminate an agent (records a `KillResult`).
> 7. `backend/app/governance/reliability.py` — per-agent circuit breakers + SLO counters.
> 8. `backend/app/governance/intake.py` — the governed intake: PII redaction + injection scan + prompt-defense grade + NSE symbol resolution.
> 9. `backend/app/api/routes_governance.py` — every dashboard endpoint, including the `/demo/*` routes, in one file.

---

## 16. Configuration & environment variables

All config is read from `backend/.env` (gitignored — you create it). **The app
runs with no keys** (research/market data use deterministic mocks). Add keys to
turn on live providers.

| Variable | Enables |
|----------|---------|
| `GROQ_API_KEY` | Live LLM for the Strategy thesis (Groq) |
| `GROQ_MODEL` | Which Groq model the Strategy agent uses |
| `GEMINI_API_KEY` | LLM fallback + RAG embeddings |
| `TAVILY_API_KEY` | Live news/research (Research agent) |
| `FINNHUB_API_KEY` | Live market quotes (Market‑Data agent) |
| `ALPHAVANTAGE_API_KEY` | Fallback market data |
| `JEV_API_KEY` | JEV via **OpenRouter** Decisions API (primary judge) |
| `JEV_MODEL` | OpenRouter judge model (default `typesafe/jev-1.13`, the TypeSafe Jev decision model) |
| `GROQ_MODEL_2` | **Second Groq key** → JEV fallback when `JEV_API_KEY` is unset |
| `GROQ_JEV_MODEL` | Groq fallback judge model (default `openai/gpt-oss-20b`) |
| `AGT_AUDIT_SECRET_KEY` | Enables a persistent, signed audit sink |
| `GOVDESK_PORT` / `GOVDESK_HOST` / `GOVDESK_CORS_ORIGINS` | Server config |

> **JEV key tip:** `GROQ_MODEL_2` is deliberately a *second* Groq API key (not a
> model name — the name is historical). Keeping it separate from `GROQ_API_KEY`
> gives JEV its own rate‑limit budget so judging doesn't compete with the
> Strategy agent.

---

## 17. How to run it locally

**Prerequisites:** Python 3.11+ and Node 18+.

**Backend** (terminal 1):
```bash
cd research_governance/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
```
→ API at http://127.0.0.1:8099 (interactive docs at `/docs`).

**Frontend** (terminal 2):
```bash
cd research_governance/frontend
npm install
npm run dev
```
→ UI at http://localhost:5173.

> Keep the ports stable: frontend `5173`, backend `8099`. The backend's CORS
> allowlist and the frontend's default `VITE_API_BASE` assume these.

Then on the **Desk** page: type a query → **Run intake** → **Run Workflow**, and
watch the pipeline. Open **Agent Governance** to see the live dashboard.

---

## 18. How to extend it

- **Add an agent:** write a new node function in `desk_graph.py` (call
  `gate.evaluate` first), add it to the `_PIPELINE` list in `desk_stream.py`,
  give it a policy YAML, and register it in `identities.py`.
- **Change a rule:** edit the agent's `policies/*.yaml` and restart the backend.
  (Policies are deterministic YAML loaded into the AGT `PolicyEngine`.)
- **Swap the JEV model:** set `JEV_MODEL` (OpenRouter) or `GROQ_JEV_MODEL`
  (Groq). To change the judging prompt, edit `_SYSTEM_PROMPT` in `jev.py`.
- **Add a dashboard panel:** add an endpoint in `routes_governance.py`, an
  `api.*` function + type, and a new component in `components/`, then mount it in
  `AgentGovernance.tsx`.
- **Add a REST call:** add the function to `lib/api.ts` and the response type to
  `lib/types.ts` — that's the whole frontend‑side contract.

---

## 19. Honest limitations

Say these out loud in a demo — they build credibility.

- **It's a demo, not a trading system.** Only trade *placement* is simulated.
- **The DB resets on every backend restart** (fresh identities per process).
- **The deterministic policy engine is the real guarantee.** The probabilistic
  layers (advisory, JEV) only *tighten* an allow; they can't loosen a deny.
- **Prompt‑injection and prompt‑defense are signature/heuristic based.** They
  catch known patterns, not every possible attack. (A misspelled or reworded
  injection can slip past the detector — this is a known property, not a bug.)
- **JEV scores depend on an external LLM** and its rate limits; without a key,
  JEV is honestly shown as "unavailable" and is non‑blocking.
- **The LangGraph adapter is not relied on for the guarantee** — governance is
  enforced by calling the gate directly in each node.

---

## 20. Glossary

- **AGT** — Agent Governance Toolkit, the Microsoft open‑source library this
  project is built on (imported in‑process).
- **Agent** — one governed step in the desk (Research, Market‑Data, Strategy,
  Risk, Execution, Governance). Each has a cryptographic identity.
- **DID** — Decentralized Identifier, e.g. `did:mesh:abc…`, an agent's Ed25519
  cryptographic identity.
- **Gate** — `GovernanceGate.evaluate()` in `gate.py`; the one place every
  action is checked, audited, scored, and recorded.
- **Policy** — a YAML file of `condition → action` rules the deterministic
  engine evaluates. One per agent in `policies/`.
- **Verdict** — the result of a policy check: `allow`, `deny`, or
  `require_approval` (plus advisory `flag`/`block`).
- **JEV** — the per‑agent safety judge: a real LLM scoring each agent's output
  0–1; below 0.5 blocks the pipeline.
- **Ring** — an execution privilege level (RING_2 = network allowed, RING_3 =
  sandbox) that limits what an agent may touch.
- **Shadow agent** — an agent found running that is *not* registered with
  governance (no identity/owner) — what discovery hunts for.
- **Advisory** — the probabilistic layer that runs after a deterministic allow
  on a trade and may only tighten it.
- **REST / WebSocket / SSE** — the three ways the frontend talks to the backend:
  request/response, an always‑on live decision feed, and the one‑shot ordered
  pipeline stream, respectively.
- **Paper / simulated order** — the Execution agent never contacts a real
  broker; it logs a simulated order.

---

### TL;DR

GovDesk is a 6‑agent financial research desk where **every agent action is
governed by deterministic AGT policy before it runs**, attributed to a
cryptographic identity, recorded in a tamper‑evident audit log, trust‑scored,
layered with MCP tool security / execution sandboxing / a probabilistic advisory
/ shadow discovery / marketplace vetting, and now **re‑checked by a JEV safety
judge after every agent**. The React frontend talks to the FastAPI backend over
**REST** (queries/actions), a **WebSocket** (live decisions), and **SSE** (the
real‑time agent pipeline). The one file to understand above all others is
`backend/app/governance/gate.py`.

---

## 21. Complete codebase reading order (every file)

This is the single front‑to‑back path to read **every source file** in the
project and understand how it fits. Open each file in this order; the §
reference points back to the section that explains *why* that file matters.
Config, cache, and generated files (`__pycache__`, `_rag_cache`, `.env`,
`node_modules`, `dist`, `tsconfig.tsbuildinfo`) are intentionally skipped.

### Phase A — Orientation (read before any code)
1. `research_governance/README.md` — quick start + feature summary.
2. `research_governance/explain.md` — this document.
3. `research_governance/plan.md` — the original design doc (historical context).

### Phase B — Backend foundations (§6, §13)
4. `backend/requirements.txt` — the Python dependencies.
5. `backend/.env.example` — every environment variable, with placeholders.
6. `backend/app/config.py` — AGT import bootstrap + `Settings`. **Read first.**
7. `backend/app/store/db.py` — the SQLite schema + all read/write functions.
8. `backend/app/main.py` — FastAPI app, CORS, startup, WebSocket + SSE wiring.

### Phase C — Identities, policies, the gate (§7, §8)
9.  `backend/app/governance/identities.py` — the 6 agents + Ed25519 DIDs.
10. `backend/app/policies/execution.yaml` — the richest policy.
11. `backend/app/policies/risk.yaml` — numeric limit + instrument blocklist.
12. `backend/app/policies/research.yaml`
13. `backend/app/policies/market_data.yaml`
14. `backend/app/policies/strategy.yaml`
15. `backend/app/governance/gate.py` — **the heart.** Read `evaluate()` slowly.
16. `backend/app/governance/advisory.py` — the probabilistic advisory classifier.

### Phase D — The agents and what they call (§7)
17. `backend/app/graph/state.py` — `DeskState`.
18. `backend/app/integrations/providers.py` — Tavily / Finnhub / Groq+Gemini.
19. `backend/app/integrations/rag.py` — the annual‑report RAG pipeline.
20. `backend/app/mcp/catalog.py` — MCP tool definitions (incl. demo‑malicious).
21. `backend/app/graph/desk_graph.py` — the 5 agent nodes + `run_desk()`.

### Phase E — Governance phase modules (§15)
22. `backend/app/governance/mcp_security.py` — MCP tool scanner.
23. `backend/app/governance/marketplace.py` — plugin vetting + signing.
24. `backend/app/governance/discovery.py` — shadow‑AI discovery.
25. `backend/app/governance/rings.py` — execution rings + command denylist.
26. `backend/app/governance/killswitch.py` — agent termination.
27. `backend/app/governance/reliability.py` — circuit breakers + SLO.
28. `backend/app/governance/intake.py` — PII redaction + injection + defense grade + symbol.
29. `backend/app/governance/jev.py` — the per‑agent JEV safety judge (§9).
30. `backend/app/governance/demo_controls.py` — presenter threat‑injection + reset.

### Phase F — The streaming pipeline + the HTTP API (§10)
31. `backend/app/graph/desk_stream.py` — the ordered‑event generator (SSE core).
32. `backend/app/api/routes_desk.py` — intake, run, and the SSE `run-stream` route.
33. `backend/app/api/routes_governance.py` — all dashboard + demo endpoints.
34. `backend/app/api/routes_approvals.py` — the human‑approval queue.

### Phase G — Frontend glue (§11)
35. `frontend/package.json` — scripts + dependencies.
36. `frontend/vite.config.ts` — the Vite dev server config.
37. `frontend/src/main.tsx` — React entry point.
38. `frontend/src/lib/types.ts` — every data shape (mirrors backend JSON).
39. `frontend/src/lib/api.ts` — the REST client (`fetch`).
40. `frontend/src/lib/ws.ts` — the WebSocket helper (live decisions).
41. `frontend/src/lib/pipeline.ts` — the SSE helper (agent pipeline).

### Phase H — Frontend UI (§12)
42. `frontend/src/styles.css` — the whole theme (skim).
43. `frontend/src/App.tsx` — the shell: sidebar + routes.
44. `frontend/src/pages/Desk.tsx` — the main page (query + live pipeline).
45. `frontend/src/pages/AgentGovernance.tsx` — the dashboard composition.
46. `frontend/src/pages/Policies.tsx` — rules + demo controls.
47. `frontend/src/components/AgentRoster.tsx`
48. `frontend/src/components/DecisionTimeline.tsx`
49. `frontend/src/components/ApprovalsQueue.tsx`
50. `frontend/src/components/AuditTrail.tsx`
51. `frontend/src/components/SecurityPanel.tsx`
52. `frontend/src/components/RuntimePanel.tsx`
53. `frontend/src/components/AdvisoryPanel.tsx`
54. `frontend/src/components/ShadowDiscoveryPanel.tsx`
55. `frontend/src/components/MarketplacePanel.tsx`
56. `frontend/src/components/IntakePanel.tsx`
57. `frontend/src/components/RagPanel.tsx`

### Phase I — (Optional) The AGT library internals
Only if you want to see *inside* the toolkit the POC imports. These live under
`agent-governance-python/` and are **not** part of the POC itself:
- `agent-mesh/src/agentmesh/governance/policy.py` — the `PolicyEngine` + condition parser.
- `agent-mesh/src/agentmesh/reward/engine.py` + `reward/scoring.py` — trust scoring.
- `agent-mesh/src/agentmesh/governance/audit.py` — the hash‑chained audit log.
- `agent-os/src/agent_os/prompt_injection.py` — the injection detector (pattern‑based).
- `agent-compliance/src/agent_compliance/prompt_defense.py` — the 17‑vector defense grader.
- `agent-os/src/agent_os/mcp_security.py` — the MCP scanner.
- `agent-sre/src/agent_sre/cascade/circuit_breaker.py` — the breaker.
- `agent-hypervisor/src/hypervisor/rings/enforcer.py` + `security/kill_switch.py` — rings + kill switch.
- `agent-discovery/` and `agent-marketplace/` — discovery + marketplace.

### Suggested checkpoints
- **After Phase C** you understand the deterministic guarantee (the gate + policies).
- **After Phase D** you can trace one full agent run end to end.
- **After Phase F** you understand how a run streams to the browser.
- **After Phase H** you can follow any dashboard number back to its backend endpoint.
