# Agent Governance Toolkit — Feature Catalogue

> A decision-useful map of everything AGT can do, so you can decide **when to incorporate each feature in your internal agent/LLM services.**
>
> This is a personal reference document (not official project docs). It is filtered for practical adoption, not an exhaustive API dump. Maturity labels are based on reading the code in this checkout.

## How to read the maturity labels

| Label | Meaning |
|-------|---------|
| 🟢 **REAL** | Works out of the box, pure Python, no external service. Safe to adopt directly. |
| 🟡 **NEEDS-EXTERNAL** | Core logic is real, but it needs an external tool/service to do anything useful (OPA binary, Redis, Azure, FastAPI, an HMAC key, a target framework, etc.). |
| 🟠 **PARTIAL / PREVIEW** | Self-labeled "Public Preview", a stub, or only partially wired. Usable for experimentation; verify before production. |

### Important structural facts (read once)

- The Python import roots `agent_os` and `agentmesh` emit a **DeprecationWarning**; the real distribution is `agent-governance-toolkit-core`. The code is still real and working, these are consolidation shims. The warning is harmless.
- `agent-runtime`, `agent-hypervisor`, `agent-sre` are **deprecated facades** that re-export working code from the consolidated packages. `agent-mcp-governance` is an **empty** facade (the real MCP security lives in `agent_os`).
- `policy-engine/` (the Rust ACS) `core/` is a shim over the `agent-control-spec` crate.
- **The core enforcement, identity, audit, trust, and compliance layers are all 🟢 REAL and pure-Python.** That's the surface to build internal services on.

---

## 1. Summary table

| Feature | Layer | Import / entry | Maturity | Dep | Use it when… |
|---------|-------|----------------|:--------:|-----|--------------|
| **AGT Lite `govern()`** | Policy | `agent_os.lite.govern` | 🟢 | none | You want a 3-line allow/deny gate with zero config. |
| **`govern()` wrapper** | Policy | `agentmesh.governance.govern` | 🟢 | none¹ | Wrap any tool so every call is policy-checked + audited. |
| **PolicyEngine** | Policy | `agentmesh.governance.policy.PolicyEngine` | 🟢 | none | You need YAML/JSON rules, conflict strategies, rate limits, programmatic eval. |
| **Rego / OPA backend** | Policy | `PolicyEngine.load_rego` | 🟡 | `opa` CLI | Rules the YAML DSL can't express (field-vs-field, complex logic). |
| **Cedar backend** | Policy | `PolicyEngine.load_cedar` | 🟡 | cedarpy/CLI | You standardize on AWS Cedar policy language. |
| **ACS runtime (Rust)** | Policy | `agent_control_specification` | 🟡 | compiled core | Language-neutral, formally-specified decision runtime; native framework guards. |
| **AgentIdentity / DID** | Identity | `agentmesh.identity.agent_id` | 🟢 | none | You need cryptographic (Ed25519) per-agent identity + signing. |
| **Revocation / Rotation** | Identity | `agentmesh.identity.revocation` / `.rotation` | 🟢 | none | Revoke/rotate agent credentials. |
| **Entra / Managed Identity** | Identity | `agentmesh.identity.entra` | 🟡 | Azure | Enterprise identity backed by Microsoft Entra. |
| **mTLS / SPIFFE** | Identity | `agentmesh.identity.mtls` / `.spiffe` | 🟡 | PKI/SPIFFE | Workload identity in a service mesh. |
| **Trust scoring (RewardEngine)** | Trust | `agentmesh.reward.engine.RewardEngine` | 🟢 | none | Score agents 0–1000 on behavior; auto-revoke bad actors. |
| **Trust cards / levels / handshake** | Trust | `agentmesh.trust.*` | 🟢 | none | Peer-to-peer trust negotiation between agents. |
| **AuditLog + Merkle chain** | Audit | `agentmesh.governance.audit.AuditLog` | 🟢 | none | Tamper-evident, hash-chained record of every decision. |
| **FileAuditSink (persistent)** | Audit | `agentmesh.governance.audit_backends.FileAuditSink` | 🟡 | HMAC key ≥32B | Persist the audit trail to disk, signed. |
| **CloudEvents / OTLP export** | Audit | `AuditEntry.to_cloudevent`, `agent_os.event_sink` | 🟡 | collector | Ship governance events to your observability stack. |
| **Credential redactor** | Safety | `agent_os.credential_redactor` | 🟢 | none | Strip secrets/PII from logs and agent I/O. |
| **Prompt injection detector** | Safety | `agent_os.prompt_injection` | 🟢 | none² | Heuristic detection of injection in prompts/content. |
| **PromptDefenseEvaluator** | Compliance | `agent_compliance.prompt_defense` | 🟢 | none | Grade a system prompt (A–F) against 17 attack vectors pre-deploy. |
| **MCP Security Scanner** | MCP | `agent_os.mcp_security.MCPSecurityScanner` | 🟢³ | none | You connect agents to MCP tools; scan for poisoning/rug-pull/typosquat. |
| **MCP Gateway / Response Scanner** | MCP | `agent_os.mcp_gateway`, `.mcp_response_scanner` | 🟢 | none | Intercept MCP tool calls + sanitize responses. |
| **MCP message signing** | MCP | `agent_os.mcp_message_signer` | 🟢 | none | Sign/verify MCP envelopes. |
| **Execution Rings** | Runtime | `hypervisor.rings.enforcer.RingEnforcer` | 🟢 | none | Enforce privilege tiers (network/fs/subprocess scope) per agent. |
| **Command denylist** | Runtime | `hypervisor.sandbox` + RingEnforcer | 🟢 | none | Block dangerous shell commands structurally. |
| **Kill Switch** | Runtime | `hypervisor.security.kill_switch.KillSwitch` | 🟢 | none | Emergency-terminate a misbehaving agent. |
| **Rate limiter** | Runtime | `hypervisor.security.rate_limiter` | 🟢 | none | Cap an agent's action rate. |
| **Delta engine (audit)** | Runtime | `hypervisor.audit.delta.DeltaEngine` | 🟢 | none | Hash-chained record of state changes. |
| **Reversibility / Saga** | Runtime | `hypervisor.saga.orchestrator` | 🟠 | none | Multi-step transactions with compensation/rollback. |
| **SLO engine + error budgets** | SRE | `agent_sre.slo` | 🟢 | none⁴ | Track reliability objectives for agent services. |
| **Circuit breaker** | SRE | `agent_sre.cascade.circuit_breaker` | 🟢 | none | Stop cascading failures across agents. |
| **Chaos / adversarial engine** | SRE | `agent_sre.chaos` | 🟠 | none | Inject faults + adversarial attacks to test resilience. |
| **`agt verify` (OWASP ASI)** | Compliance | CLI / `agent_compliance.verify` | 🟢 | none | Produce an OWASP ASI compliance attestation. |
| **`agt integrity`** | Compliance | CLI / `agent_compliance.integrity` | 🟢 | none | Prove governance code wasn't tampered (file+bytecode hashes). |
| **`agt lint-policy` / `agt test`** | Compliance | CLI | 🟢 | none | Validate and regression-test policy files in CI. |
| **`agt red-team scan`** | Compliance | CLI | 🟢 | none | Audit prompts for injection defenses. |
| **`agt cred` (vault)** | Compliance | CLI / `agent_os.credential_vault` | 🟡 | Fernet key | Encrypted credential vault for tool calls. |
| **SecurityScanner** | Compliance | `agent_compliance.security.scanner` | 🟡 | detect-secrets/pip-audit/bandit/npm | Scan plugin dirs for secrets/CVEs/dangerous code. |
| **Shadow AI discovery** | Discovery | `agent_discovery` | 🟢⁵ | none | Find unregistered agents across processes/configs/repos. |
| **Marketplace trust/quality** | Marketplace | `agent_marketplace` | 🟢 | none | Govern + trust-score plugins before install. |
| **RL training governance** | Lightning | `agent_lightning_gov` | 🟡 | Agent-Lightning | Penalize policy violations during RL training. |
| **HTTP servers** | Serving | `agentmesh.server.*`, `agentmesh.engine_api` | 🟡/🟠 | FastAPI | Expose governance over HTTP (see §7 for stub caveats). |
| **Framework adapters** | Integration | `agent_os.integrations.*` | 🟡 | target framework | Native governance for LangChain/CrewAI/AutoGen/etc. |

¹ `govern()` is pure-Python unless you enable `audit_file` (needs HMAC key) or `rego_path` (needs OPA).
² Embedding-based variant needs a model; the base heuristic detector needs nothing.
³ Engine is real; it ships **SAMPLE** rules with a disclaimer to customize before production.
⁴ Optional persistence/dashboard backends.
⁵ Local process/config scanners are real; the GitHub repo scanner needs a token.

---

## 2. Policy enforcement — the core

**What it is:** deterministic allow/deny/require_approval evaluation of agent actions *before* they execute. This is AGT's reason to exist.

- **AGT Lite `govern()`** — `agent_os.lite.govern(allow=[...], deny=[...])`. Returns a callable gate; `deny` beats `allow` (fail-secure). Inline audit + stats. **Adopt when:** you want the absolute minimum, "block these, allow those," in a single service with no YAML.
- **`govern()` wrapper** — `agentmesh.governance.govern(fn, policy="policy.yaml")`. Wraps a tool so every call is policy-checked, audited, and raises `GovernanceDenied` on block. Supports `require_approval`, advisory classifiers, execution rings, and signed audit. **Adopt when:** you want to govern a specific tool/function in-process with full features.
- **PolicyEngine** — `PolicyEngine().load_yaml_file(p).evaluate(did, context)`. Direct control: conflict strategies (`deny_overrides`, `most_specific_wins`, …), rate limiting, policy inheritance (`extends`, additive-only). **Adopt when:** you want to evaluate policy yourself and route the decision.

> ⚠️ **Gotcha:** `PolicyEngine` only considers policies whose `agents` list contains the DID or `"*"`. A policy with no `agents` applies to nobody → everything denies by default. `govern()` adds the wildcard for you; direct `PolicyEngine` use does not.

**When NOT to use:** a pure chatbot with no side-effecting actions. There's nothing to gate.

### Rego / OPA and Cedar backends 🟡
`PolicyEngine.load_rego()` / `load_cedar()`. Use these only for logic the YAML DSL can't express (field-vs-field comparisons, set logic). Both need an external evaluator (`opa` CLI or cedarpy/CLI) and fall back to a limited mock if absent. **Adopt when:** your policies outgrow the simple condition DSL.

### ACS runtime (Rust core + bindings) 🟡
`agent_control_specification` (`AgentControl`, `HostSession`). A language-neutral, formally-specified decision runtime with a closed verdict set (`allow` / `deny` / `transform`), fail-closed `runtime_error:*`, and native framework **guards** (`guard_langchain_tool`, `guard_openai_client`, `guard_mcp_server`, …). **Adopt when:** you want the strongest, spec-conformant mediation across multiple languages/frameworks and can ship the compiled core.

---

## 3. Identity — "which agent did this?"

- **AgentIdentity / AgentDID** 🟢 — `AgentIdentity.create(name, sponsor=, capabilities=)`. Ed25519 keypair, `did:mesh:...` identifier, `.sign()`/`.verify_signature()`, capability-scoped delegation. **Adopt when:** multiple agents share infrastructure and you must attribute actions to a specific one.
- **Revocation / Rotation** 🟢 — revoke or rotate credentials. **Adopt when:** an agent is compromised or on a key-rotation schedule.
- **Entra / Managed Identity / mTLS / SPIFFE** 🟡 — enterprise identity backends. **Adopt when:** you already run Azure Entra or a SPIFFE/mTLS service mesh and want agents to use it.

> ⚠️ A locally generated `did:mesh` is **not** self-certifying (random, not key-derived). Only registry-issued DIDs are cryptographically bound to a key. Authenticate the DID's key through a trusted registry; don't trust a caller-supplied key.

---

## 4. Trust scoring — behavioral reputation

- **RewardEngine** 🟢 — `RewardEngine().record_signal(did, DimensionType.X, value, source=)` then `get_agent_score(did)`. Scores 0–1000 across 5 runtime dimensions (**policy_compliance, resource_efficiency, output_quality, security_posture, collaboration_health**), with tiers, explanation breakdown, at-risk list, and **automatic revocation** below a threshold. **Adopt when:** you want agents' privileges to adapt to their behavior over time, not just static rules.
- **Trust cards / levels / handshake** 🟢 — peer trust negotiation and verifiable agent cards. **Adopt when:** agents from different owners must establish trust before collaborating.

> Note: the "5 dimensions" named in some marketing (competence/integrity/availability/predictability/transparency) are a **wire-protocol enum only**. The runtime-scored dimensions are the five above.

---

## 5. Audit & evidence — "can you prove it?"

- **AuditLog + MerkleAuditChain** 🟢 — `AuditLog().log(...)`, `verify_integrity()`, Merkle inclusion proofs, CloudEvents export. Tamper-evident by hash chain. **Adopt when:** you need a defensible record of every decision (compliance, incident response, regulators).
- **FileAuditSink** 🟡 — persistent, HMAC-signed JSON-lines. Needs a ≥32-byte key (arg or `AGT_AUDIT_SECRET_KEY`). **Adopt when:** the audit trail must survive process restarts and resist tampering on disk.
- **Event sink SPI (Stdout/OTLP)** 🟡 — stream governance events to stdout or an OTLP collector. **Adopt when:** you want governance events in your existing observability pipeline.

---

## 6. Safety scanners — probabilistic detectors (advisory, not enforcement)

These are *detectors*, use them to flag/advise, not as the hard allow/deny boundary.

- **Credential redactor** 🟢 — strip secrets/PII (regex, lookaround-anchored). **Adopt when:** agent I/O or logs may contain secrets/PII.
- **Prompt injection detector** 🟢 — heuristic injection detection. **Adopt when:** agents consume untrusted text (user input, retrieved docs).
- **PromptDefenseEvaluator** 🟢 — static grade (A–F) of a system prompt against 17 OWASP vectors; deterministic, no LLM/network. **Adopt when:** gating prompt changes in CI before deploy.
- **MCP Security suite** 🟢 — scanner (tool poisoning, rug-pull/drift, typosquatting, hidden instructions), gateway (intercept + approve), response scanner (strip injected instructions), message signing. **Adopt when:** your agents use MCP tools, especially third-party ones.

---

## 7. Execution control (runtime / hypervisor)

- **Execution Rings** 🟢 — `RingEnforcer` maps privilege tiers to concrete constraints (network allowlist, filesystem scope, subprocess, concurrency). **Adopt when:** different agents need different blast radii.
- **Command denylist** 🟢 — block dangerous shell commands structurally. **Adopt when:** any agent can spawn subprocesses.
- **Kill Switch** 🟢 — terminate an agent with callbacks + in-flight handoff. **Adopt when:** you need an emergency stop.
- **Rate limiter** 🟢 — cap action rate per agent.
- **Delta engine** 🟢 — hash-chained record of state changes.
- **Reversibility / Saga orchestrator** 🟠 (Public Preview) — multi-step transactions with compensation. **Adopt when:** an agent workflow must roll back cleanly on failure; verify behavior first.

---

## 8. SRE — reliability for agent fleets

- **SLO engine + error budgets** 🟢 — objectives, SLIs, burn rate, validator. **Adopt when:** agent services have reliability targets.
- **Circuit breaker** 🟢 — per-agent CLOSED/OPEN/HALF_OPEN. **Adopt when:** a failing agent/dependency could cascade.
- **Chaos / adversarial engine** 🟠 (Public Preview) — fault injection incl. adversarial playbooks (prompt injection, privilege escalation, data exfiltration). Powers `agt red-team attack`. **Adopt when:** you want to proactively test governance under attack; it's preview-grade.

---

## 9. Compliance & CLI

All support `--json` for machine-readable output a UI/CI can consume.

- **`agt verify`** 🟢 — OWASP ASI 2026 attestation (ASI-01…ASI-10), signed, with coverage % and A–F grade. **Adopt when:** you need compliance evidence or a CI gate. *(Verified: runs and produces an attestation. Coverage depends on which governance modules are importable — against a full `agent-governance-toolkit[full]` install it checks all 10; against a partial checkout one or two controls may read as absent.)*
- **`agt integrity`** 🟢 — verify/generate SHA-256 manifest of governance source + function bytecode ("who watches the watcher"). **Adopt when:** you must prove the governance layer itself wasn't subverted.
- **`agt lint-policy` / `agt test`** 🟢 — validate policy files; replay test fixtures (exit 1 on mismatch). **Adopt when:** gating policy changes in CI.
- **`agt doctor`** 🟢 — installation health.
- **`agt red-team scan`** 🟢 — prompt-defense audit over a directory.
- **`agt cred`** 🟡 — Fernet-encrypted credential vault for tool calls (needs `AGT_VAULT_KEY`).
- **SecurityScanner** 🟡 — secrets/CVE/SAST scan; a no-op without `detect-secrets`/`pip-audit`/`bandit`/`npm`.

> **Compliance reality check:** the **real, implemented** mapping is **OWASP ASI (ASI-01…10)**. SOC 2 / NIST AI RMF / EU AI Act appear in docs and as keyword buckets but are **not** implemented control mappings in code. Treat those as documentation, not automated checks.

---

## 10. Discovery, marketplace, RL

- **Shadow AI discovery** 🟢 — `agent_discovery` inventories agents and flags unregistered ("shadow") ones via process/config scanners, with reconciliation and risk scoring. (GitHub repo scanner needs a token 🟡.) **Adopt when:** you need to find agents running outside governance.
- **Marketplace trust/quality** 🟢 — `agent_marketplace` scores plugins (trust tiers, usage signals, quality) and signs artifacts before install. **Adopt when:** you install third-party agent plugins.
- **RL training governance** 🟡 — `agent_lightning_gov` turns policy violations into RL penalties. **Adopt when:** you train agents with RL and want governance baked into the reward.

---

## 11. HTTP serving surfaces — mind the stubs

- **`policy_server`** 🟡 — real policy evaluation over HTTP (`POST /api/v1/policy/evaluate`). **Caveat:** accepts `agent_did` from the body **without authenticating the caller** (documented gap). Put auth in front before trusting it.
- **`audit_collector` / `trust_engine`** 🟡 — real audit and trust services over HTTP.
- **`engine_api` ("Studio Engine API")** 🟠 — policy read/validate/test/save endpoints are **real**; but `/audit/log`, `/agents`, `/trust/scores`, `/decisions` are **placeholder stubs** returning empty data (tracked by issue #2729). The schemas are stable; the data isn't wired.
- **Governance dashboard (Streamlit demo)** 🟠 — fed by **synthetic data only**; a UI reference, not a data source.

> **For a unified dashboard across many services:** AGT gives you the emitters (audit, trust, decisions) and the data models, but **not** the central aggregation. You supply a shared store (e.g. Postgres) that each service writes to and the dashboard reads from. See the `examples/demos/governance-workflow` demo for the library-direct pattern.

---

## 12. Cross-language coverage

Core governance (policy, identity, trust, audit, MCP security, execution rings, SRE, kill switch, lifecycle, shadow discovery, prompt defense) is implemented in **all five SDKs**: Python, TypeScript, .NET, Rust, Go.

**Python-only today:** the unified `agt` CLI, OWASP verification, the governance dashboard, and the 20+ framework adapters. **.NET** identity is partial (uses native ECDSA rather than Ed25519). For non-Python internal services, the native SDK gives you the four core primitives; reach for Python when you need the CLI/verification/adapters.

---

## 13. Decision guide — what to adopt first

A pragmatic adoption ladder for an internal agent/LLM service:

1. **Start:** `govern()` + a YAML policy + in-memory `AuditLog`. Deterministic enforcement + a decision trail, pure Python, zero deps. *(This is what the `governance-workflow` demo runs.)*
2. **Add identity** (`AgentIdentity`) when more than one agent shares infrastructure.
3. **Persist audit** (`FileAuditSink` + HMAC key) when you need durable, tamper-evident evidence.
4. **Add trust scoring** (`RewardEngine`) when you want behavior-adaptive privileges + auto-revocation.
5. **Add execution rings + kill switch** when agents touch the filesystem/network/subprocesses.
6. **Add MCP security** when agents use MCP tools (especially third-party).
7. **Add compliance** (`agt verify`, `agt integrity`, `agt lint-policy` in CI) when you need evidence and gates.
8. **Scale out:** emit audit/trust/decisions to a shared store and build the cross-service dashboard yourself (AGT provides emitters + schemas, not aggregation).

**Rule of thumb:** use the **libraries directly, in-process** for enforcement (tightest, safest, fastest). Reach for the **HTTP servers** only for cross-language access or a deliberately-separated central authority, and remember the dashboard-style read endpoints are stubs today.
