# Understanding GovDesk — a complete walkthrough

This document explains the project from the ground up, assuming you have **not**
read any of the code yet. It goes in this order:

1. What problem this solves (the big idea)
2. The mental model (deterministic vs probabilistic governance)
3. The overall architecture (how the pieces fit)
4. The request lifecycle (what happens when you click "Run")
5. Each phase: what it adds, how it works, and **which files to read**
6. A guided reading order so you can learn the codebase efficiently
7. Glossary

Read it top to bottom once; then use section 5/6 as a map when you open the code.

---

## 1. What problem does this solve?

Modern AI "agents" don't just chat — they **take actions**: search the web,
read market data, draft proposals, place trades. Once an agent can act, three
questions matter:

1. **Is this action allowed?** (An agent with a trading tool shouldn't be able to
   wipe a database or place a $10M order.)
2. **Which agent did it?** (If five agents share one system, "an agent did it" is
   not an answer.)
3. **Can you prove what happened?** (Auditors/regulators need a tamper-proof record.)

**GovDesk** is a realistic multi-agent "financial research desk" built to show
how the **Microsoft Agent Governance Toolkit (AGT)** answers those three
questions. It is a *demonstration*: it does real research, real market data, and
real LLM reasoning, but it never places a real trade (the final step is a
simulated "paper" order).

The project lives entirely under `research_governance/` and does not modify the
AGT toolkit itself — it *uses* AGT as a library.

---

## 2. The mental model: deterministic vs probabilistic

This is the single most important idea in the whole project.

- **LLM guardrails** (asking the model nicely, or using another model to judge
  output) are **probabilistic**. They work most of the time but can be fooled,
  and they can't *guarantee* a bad action won't happen.
- **AGT governance** is **deterministic**. Before an action runs, plain code
  evaluates a policy rule and returns allow/deny. A denied action is not
  "unlikely" — it is *structurally impossible*, because the check happens in
  regular Python before the action executes.

GovDesk uses **both**, in the correct order:

- The **deterministic policy engine** makes the hard allow/deny decision.
- A **probabilistic advisory layer** (Phase 4) runs *after* a deterministic
  allow and may only *tighten* it (flag or block) — never loosen it.

Keep this in mind: everywhere you see a "gate," the deterministic check is the
real guarantee; the probabilistic parts are advisory.

---

## 3. Architecture — how the pieces fit

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND  (research_governance/frontend)   React + Vite + TypeScript│
│   • Desk page         — trigger a research→trade cycle              │
│   • Agent Governance  — the dashboard (all the panels)              │
│   • Policies page     — the active rules                            │
└───────────────┬───────────────────────────────┬────────────────────┘
                │ REST (fetch)                   │ WebSocket (live decisions)
                ▼                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  BACKEND  (research_governance/backend)   FastAPI + LangGraph + AGT │
│                                                                     │
│   LangGraph "desk graph": research → market_data → strategy →       │
│                            risk → execution                         │
│                                                                     │
│   The governance "gate" wraps every step. It uses AGT libraries:    │
│     • PolicyEngine   (deterministic allow/deny)                     │
│     • AgentIdentity  (who did it — Ed25519 DIDs)                    │
│     • AuditLog       (tamper-evident hash chain)                    │
│     • RewardEngine   (trust scores)                                 │
│     • MCPSecurityScanner, RingEnforcer, KillSwitch, CircuitBreaker, │
│       advisory, discovery, marketplace  (phases 2–5)                │
└───────────────┬────────────────────────────────────────────────────┘
                │                                 external (live) APIs
                ▼                                 ───────────────────
         SQLite  (govdesk.db)                     Tavily  (news)
         tables: agents, decisions,               Finnhub (quotes)
         audit_entries, trust_scores,             Groq / Gemini (LLM)
         approvals, mcp_scans, runtime_events,
         shadow_agents, plugin_vettings
```

Two things worth internalizing:

- **The frontend can't call Python directly.** React talks to the backend over
  HTTP + a WebSocket; the backend calls the AGT libraries *in-process*. The
  governance guarantee lives in the backend, not the UI.
- **The backend resets its database on every startup.** Agent identities are
  minted fresh each run, so the roster, decisions, audit, etc. always reflect
  the current process. (Durable history across restarts would need stable
  identities — a deliberate simplification.)

---

## 4. The request lifecycle — what happens when you click "Run"

Say you run `AAPL`, `$500` on the Desk page:

1. **Frontend** POSTs `{symbol: "AAPL", amount: 500}` to `/api/desk/run`.
2. **Backend** starts the **LangGraph desk graph** with that input.
3. The graph runs node by node. **Each node calls the governance gate first:**
   - `research` → gate checks the research policy (allow) + ring (needs network)
     + circuit breaker, then calls **Tavily** for live headlines.
   - `market_data` → gate checks policy + ring + **picks an MCP tool that passed
     security scanning**, then calls **Finnhub** for the live price.
   - `strategy` → gate checks policy, then calls **Groq/Gemini** for a thesis.
   - `risk` → gate checks the risk policy (size limits, blocked instruments).
   - `execution` → gate checks the execution policy. Small trade → **allow**;
     ≥ $100k → **require approval** (routes to a human queue); then the
     **advisory layer** runs and may flag/block.
4. **Every gate call** writes a decision + a hash-chained audit entry, updates
   the agent's trust score, and **broadcasts the decision over the WebSocket**
   so the dashboard's timeline updates live.
5. The graph returns a final status: `completed`, `blocked`, or
   `pending_approval`. The result is a **simulated** paper order.

If any step is denied, the graph stops there and reports what blocked it.

---

## 5. The phases — what each adds, how it works, which files to read

The project was built in 5 phases. Each phase is a layer of AGT governance. All
the governance wiring lives in `backend/app/governance/`.

### Foundations (read these first — they underpin every phase)

| File | What it does | What to look for |
|------|--------------|------------------|
| `backend/app/config.py` | Boots everything. Puts the local AGT source trees on `sys.path` so `import agentmesh`, `agent_os`, etc. work; loads `.env` settings. | The `_AGT_SRC_DIRS` list and `Settings` dataclass. This is *why* the AGT imports resolve. |
| `backend/app/store/db.py` | The SQLite store. One table per kind of record. | Scan the `_SCHEMA` string — every table maps to something you see in the UI. |
| `backend/app/governance/identities.py` | Creates a cryptographic `AgentIdentity` (Ed25519 DID) for each of the 6 agents. | `_AGENT_SPECS` (the 6 agents + their rings/capabilities) and `AgentIdentity.create(...)`. |
| `backend/app/governance/gate.py` | **The heart of the project.** Every action flows through `GovernanceGate.evaluate()`. | Read `evaluate()` slowly — it ties policy + audit + trust + advisory together and is where phases plug in. |

### Phase 1 — core governance (policy, identity, audit, trust, approvals)

**Idea:** every agent action is checked against a deterministic YAML policy,
attributed to an identity, recorded in a tamper-evident audit log, and scored.

**How it works:** each agent has its own policy file. The gate loads it into an
AGT `PolicyEngine`. On each action, `engine.evaluate(did, {"action": {...}})`
returns `allow` / `deny` / `require_approval`. The gate then logs to an
`AuditLog` (hash-chained) and feeds a signal to a `RewardEngine` (trust score).
High-value trades return `require_approval`, which the graph turns into a human
approval record.

**Files to read:**
- `backend/app/policies/*.yaml` — the 5 agent policies. Start with
  `execution.yaml` (shows numeric + compound conditions and `require_approval`)
  and `risk.yaml` (blocked instruments, max size). **Note:** every policy has
  `agents: ["*"]` — without it the engine treats the policy as applying to
  nobody (a gotcha we hit during the build).
- `backend/app/governance/gate.py` — `evaluate()` is the whole Phase 1 flow.
- `backend/app/graph/desk_graph.py` — the LangGraph graph; each `*_node`
  function calls `gate.evaluate(...)` before acting.
- `backend/app/graph/state.py` — the data passed between nodes.
- `backend/app/governance/identities.py` — the 6 agents.
- `backend/app/api/routes_desk.py` — the `/api/desk/run` endpoint.
- `backend/app/api/routes_approvals.py` — the human approvals queue.

**See it in the UI:** Desk page (run a cycle); Agent Governance page → Agent
roster, Decision timeline, Approvals queue, Audit trail (+ Verify integrity).

### Phase 2 — MCP tool security

**Idea:** the Market-Data agent fetches quotes through an **MCP tool**. Before
any tool is used, its definition is scanned for poisoning, hidden instructions,
typosquatting, and "rug pulls." A tool with a CRITICAL finding is blocked.

**How it works:** there's a catalog of MCP tools, including two intentionally
malicious ones (a poisoned tool with a hidden instruction, and a typosquat).
AGT's `MCPSecurityScanner` scans each. The market_data node will only use a tool
that passed, so the poisoned tool can never influence a trade.

**Files to read:**
- `backend/app/mcp/catalog.py` — the tool definitions, including the
  `demo_malicious` ones. Read the descriptions to see the planted threats.
- `backend/app/governance/mcp_security.py` — wraps `MCPSecurityScanner`;
  `scan_catalog()` and `is_tool_allowed()`.
- In `backend/app/graph/desk_graph.py`, re-read `market_data_node` — it now
  picks a scanned, allowed tool before fetching.

**See it in the UI:** Agent Governance → **MCP tool security** panel
(`market_quote_pro` blocked, `finnhub_qoute` flagged).

### Phase 3 — runtime hardening (rings, denylist, kill switch, SRE)

**Idea:** limit each agent's blast radius and keep the system reliable.

**How it works:**
- **Execution rings:** each agent is pinned to a privilege ring. The Execution/
  Risk/Strategy agents are in a tight sandbox (no network, no subprocess); only
  Research/Market-Data get network. A node checks its ring before using a resource.
- **Command denylist:** dangerous shell commands (`curl`, `wget`, `bash`, …) are
  structurally blocked — this is the "egress attempt" demo.
- **Kill switch:** terminate an agent for real (records a `KillResult`).
- **Circuit breaker + SLO:** live provider calls go through a breaker; repeated
  failures trip it open and block further calls (stops cascading failures).

**Files to read:**
- `backend/app/governance/rings.py` — ring assignments + `check_resource` /
  `check_command`.
- `backend/app/governance/killswitch.py` — wraps AGT `KillSwitch`.
- `backend/app/governance/reliability.py` — per-agent `CircuitBreaker` + SLO.
- In `desk_graph.py`, see how `research_node` / `market_data_node` call the ring
  check and wrap provider calls in `reliability.call(...)`.

**See it in the UI:** Agent Governance → **Runtime hardening** panel (rings,
breaker states, kill history, "Simulate egress attempt" button).

### Phase 4 — the advisory layer (probabilistic, on top of deterministic)

**Idea:** add a "System 1" risk opinion *after* the deterministic allow. It can
**flag** (still allowed) or **block** (downgrade the allow to a deny) — but it
can never turn a deny into an allow.

**How it works:** a classifier scores a trade on size, instrument watchlist,
news sentiment, and price momentum. The gate runs it only when the deterministic
verdict was `allow`. This is exactly where a real decision model (e.g. a
Jev/Laya-style typed decision model) would plug in — the heuristic is a stand-in.

**Files to read:**
- `backend/app/governance/advisory.py` — the classifier (`_score_trade`) and how
  it maps risk to allow/flag/block. The comment points to where a real model goes.
- In `gate.py`, re-read the advisory section of `evaluate()` — note it only runs
  after a deterministic allow and uses `effective_action`/`effective_reason`.
- In `desk_graph.py`, `execution_node` passes `signals` (sentiment + momentum)
  into the gate for the advisory to consider.

**See it in the UI:** Agent Governance → **Advisory layer** panel. Try
`MEME`/`$60,000` (advisory block) vs `AAPL`/`$60,000` (advisory flag).

### Phase 5 — shadow discovery + marketplace vetting

**Idea:** find ungoverned ("shadow") agents, and vet third-party tools before
trusting them.

**How it works:**
- **Shadow discovery:** observes agents "running" (the 6 governed ones plus
  planted rogue ones), reconciles against the registry of known DIDs, and
  risk-scores anything with no identity/owner as a shadow agent.
- **Marketplace vetting:** treats each MCP tool as a signed plugin — builds a
  manifest, signs it with Ed25519, verifies it, assigns a trust tier and quality
  grade. A tool blocked by the Phase 2 scan is forced to the `revoked` tier, so
  it can't be trusted through the marketplace either.

**Files to read:**
- `backend/app/governance/discovery.py` — `_observe_governed` + `_observe_shadows`,
  the `Reconciler`, and `RiskScorer`. Note the `ThreadPoolExecutor` around the
  async reconcile (a bug fix: `asyncio.run()` can't run inside FastAPI's loop).
- `backend/app/governance/marketplace.py` — `_vet_one` builds + signs a manifest
  and composes with the MCP scan verdict.

**See it in the UI:** Agent Governance → **Shadow AI discovery** panel (3 critical
shadows) and **Marketplace vetting** panel (poisoned tool revoked).

### Phase 6 — governed intake + RAG over annual reports

**Idea:** make the entry point a plain-English request, govern it (strip PII,
block injection), resolve the company to an Indian NSE ticker, and ground the
analysis in the company's real annual report.

**How it works:**
- **Intake gate:** the user's free-text request is run through
  `CredentialRedactor` (plus Indian PAN/Aadhaar/phone patterns) to strip PII,
  then `PromptInjectionDetector` to catch injection — a detected attack blocks
  the run and shows why. The LLM extracts the company name, which is mapped to an
  NSE symbol via the NSE equity master CSV.
- **Governed RAG:** the Market-Data agent's *second* tool fetches the latest NSE
  annual-report PDF, extracts + chunks the text, embeds it with Gemini, stores it
  in ChromaDB, and retrieves the chunks most relevant to the query. Each retrieved
  chunk is injection-screened (retrieved documents are the classic indirect-
  injection vector) before any can reach the strategy LLM; the retrieval is audited.

**Files to read:**
- `backend/app/governance/intake.py` — `process()` does redact → injection scan →
  symbol resolution. Note it uses the injection detector (not PromptDefense) to
  judge *user input*.
- `backend/app/integrations/rag.py` — the NSE fetch → pypdf → chunk → Gemini embed
  → ChromaDB → retrieve pipeline, with graceful fallback at every external step.
  Note the embedding model is `models/gemini-embedding-001`.
- In `backend/app/graph/desk_graph.py`, re-read `market_data_node` (the RAG step +
  per-chunk injection screening) and `strategy_node` (feeds safe chunks into the LLM).

**See it in the UI:** Desk page — a free-text query box runs intake first (shows
PII redactions, the injection verdict, and the resolved symbol) before the run.
Agent Governance → **Governed intake** panel and **Annual-report RAG** panel.

---

## 6. Suggested reading order

If you want to actually read the code and understand it, go in this order:

1. `backend/app/config.py` — how AGT gets imported.
2. `backend/app/store/db.py` — the data shapes (skim the schema).
3. `backend/app/governance/identities.py` — the 6 agents.
4. `backend/app/policies/execution.yaml` and `risk.yaml` — what a policy looks like.
5. `backend/app/governance/gate.py` — **the core.** Read `evaluate()` carefully.
6. `backend/app/graph/desk_graph.py` — how the agents are wired into a flow and
   call the gate.
7. `backend/app/main.py` — the FastAPI app, WebSocket stream, startup.
8. `backend/app/api/routes_governance.py` — every dashboard endpoint in one file.
9. Then the phase modules as you care about them: `mcp_security.py`, `rings.py`,
   `killswitch.py`, `reliability.py`, `advisory.py`, `discovery.py`,
   `marketplace.py`.
10. Frontend: `frontend/src/lib/api.ts` (what it calls), then
    `frontend/src/pages/AgentGovernance.tsx` (how the panels compose), then the
    individual `frontend/src/components/*Panel.tsx`.

**The one file to understand above all others is `gate.py`.** Everything else
feeds into or reads from the gate.

---

## 7. Glossary

- **AGT** — Agent Governance Toolkit, the Microsoft open-source library this
  project is built on. GovDesk imports it from the local source tree.
- **Agent** — one worker in the desk (Research, Market-Data, Strategy, Risk,
  Execution, Governance). Each has a cryptographic identity.
- **DID** — Decentralized Identifier, e.g. `did:mesh:abc...` — an agent's
  cryptographic identity (Ed25519).
- **Policy** — a YAML file of rules (`condition` → `action`) the deterministic
  engine evaluates. One per agent, in `backend/app/policies/`.
- **Verdict** — the outcome of a policy check: `allow`, `deny`, or
  `require_approval` (plus the advisory's `flag_for_review` / `block`).
- **Gate** — `GovernanceGate.evaluate()` in `gate.py`; the single place every
  action is checked, audited, scored, and recorded.
- **LangGraph** — the orchestration library that runs the agents as a graph
  (research → … → execution). It handles *flow*; the gate handles *governance*.
- **MCP** — Model Context Protocol; a standard way agents connect to external
  tools. GovDesk fetches market data through an MCP tool so it can be security-scanned.
- **Ring** — an execution privilege level (0 = most powerful, 3 = sandbox) that
  limits network/filesystem/subprocess access per agent.
- **Shadow agent** — an agent found running that is not registered with
  governance (no identity/owner) — the thing discovery hunts for.
- **Advisory** — the probabilistic layer that runs after a deterministic allow
  and may only tighten it.
- **Paper/simulated order** — the Execution agent never contacts a real broker;
  it logs a simulated order. This is a demo, not a trading system.

---

## TL;DR

GovDesk is a 6-agent financial research desk where **every action is governed by
deterministic AGT policy before it runs**, attributed to a cryptographic
identity, recorded in a tamper-evident audit log, trust-scored, and layered with
MCP tool security, execution sandboxing, a probabilistic advisory check, shadow
discovery, and marketplace vetting. The React **Agent Governance** page shows all
of it live. The single most important file is
`backend/app/governance/gate.py`.
