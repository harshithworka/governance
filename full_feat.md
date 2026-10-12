# Agent Governance Toolkit (AGT) — Complete Feature Inventory

> A full, end-to-end, point-wise map of what Agent Governance Toolkit actually ships, verified against the source tree (not just `FEATURES.md`). Paths are given so you can jump straight to each capability.
>
> Scope note: the throwaway sample project `research_governance/` is intentionally excluded from this inventory.

---

## What AGT is (in plain language)

AGT is a **runtime governance toolkit for autonomous AI agents**. It sits in deterministic application code *between* an agent's intent and the real world, and intercepts every tool call, message, and delegation to decide — before execution — whether the action is allowed, who the agent is, and whether the decision is provably recorded. It bundles a policy decision engine, cryptographic agent identity, trust scoring, execution sandboxing, SRE/reliability controls, MCP-tool security, and compliance tooling, exposed through SDKs in five languages plus hook-based integrations for several agent CLIs. The core enforcement, identity, audit, trust, and compliance layers are real, pure-code, and run with no external service; several higher-level pieces (saga/rollback, chaos engine, HTTP read dashboards, some cloud identity backends) are preview-grade or require external services, and this report flags those explicitly.

---

## Why AGT vs LangSmith / Langfuse

LangSmith and Langfuse are **observability/tracing platforms**: they record what an agent *did* (traces, spans, token counts, evals, prompt versions) so you can debug and measure it after the fact. They are read/measure tools. They do not stop an action from happening.

AGT is a **control plane**, not an observability plane. Its job is to answer three questions the README frames as the reason to exist:

1. **Is this action allowed?** — A deterministic policy engine evaluates every tool call / message / delegation and returns `allow` / `deny` / `transform` / `require_approval` *before* the action runs. A denied action is structurally prevented, not just logged. (`policy-engine/`, `agentmesh.governance.govern`)
2. **Which agent did this?** — Cryptographic per-agent identity (Ed25519 DIDs), delegation chains, revocation/rotation, so a shared API key is not the unit of accountability. (`agentmesh.identity`, `agent-governance-*` SDKs)
3. **Can you prove what happened?** — A tamper-evident, hash-chained (Merkle) audit log of every decision, with integrity verification and an OWASP ASI attestation command. (`agentmesh.governance.audit`, `agt verify`, `agt integrity`)

Where the two overlap: AGT *does* emit telemetry (OpenTelemetry policy spans, CloudEvents/OTLP export, metrics) so you can ship governance events to your existing observability stack — including LangSmith/Langfuse. So the honest positioning is **complementary, not competitive**: use LangSmith/Langfuse to see and evaluate agent behavior; use AGT to enforce what agents are allowed to do, attribute it to a cryptographic identity, sandbox execution, and produce compliance evidence.

**Honesty caveats (verified in-tree):**
- Enforcement is at the **application middleware layer**, not the OS kernel — the policy engine and the agent share a process boundary. The project itself recommends per-agent containers for OS-level isolation (`docs/LIMITATIONS.md`, README "Security").
- The **only implemented compliance control-mapping is OWASP ASI** (`ASI-01…10`). SOC 2 / NIST AI RMF / EU AI Act appear in docs and as keyword buckets (e.g. `agent-compliance/.../cli/contributor_check.py`), not as automated control checks. Treat those as documentation.
- Several surfaces are preview/stub: saga rollback, chaos engine, and the Studio `engine_api` read endpoints (`/audit/log`, `/agents`, `/trust/scores`, `/decisions`) return placeholder data; the governance dashboard demo runs on synthetic data.

---

## Feature inventory by subsystem

Maturity legend: 🟢 real/pure-code · 🟡 real but needs an external service/tool/key · 🟠 preview/partial/stub.

### 1. Policy Engine (core enforcement)

- 🟢 **AGT Lite `govern()`** — minimal 3-line allow/deny gate, `deny` beats `allow`, inline audit. `agent_os.lite.govern` (`agent-governance-python/agent-os/`).
- 🟢 **`govern()` tool wrapper** — wrap any function so every call is policy-checked, audited, raises `GovernanceDenied` on block; supports `require_approval`, rings, signed audit. `agentmesh.governance.govern` (`agent-governance-python/agent-mesh/`).
- 🟢 **PolicyEngine** — YAML/JSON rules, conflict strategies (`deny_overrides`, `allow_overrides`, `most_specific_wins`, priority), rate limits, policy inheritance (`extends`). `agentmesh.governance.policy.PolicyEngine`.
- 🟡 **Rego/OPA backend** — rules beyond the YAML DSL; needs the `opa` CLI (falls back to a limited mock). `PolicyEngine.load_rego`.
- 🟡 **Cedar backend** — AWS Cedar policy language; needs cedarpy/CLI. `PolicyEngine.load_cedar`.
- 🟡 **ACS runtime (Agent Control Specification)** — stateless, deterministic, fail-closed policy *decision* runtime with a Rust core (`agt_core_engine`), consumed by host adapters at eight lifecycle intervention points. `policy-engine/` (host SDK `policy-engine/sdk/rust`, bindings for Python/Node/.NET/Go). See divergence note below.
- 🟢 **`agt-policies` migration bridge** — one-way `agt migrate v4-to-v5` policy migration + resolution (discover/scope/merge). `agent-governance-python/agt-policies/`.

> ACS verdict-model note: the root README describes a 5-verdict ACS (`allow/deny/warn/escalate/transform`), while `policy-engine/` has been retargeted onto the agent-hooks contract with a **closed 3-verdict set** (`allow`, `deny`, `transform`; a former `warn` is an allow carrying warnings, a former `escalate` is a liftable deny carrying an approval block). The `policy-engine/core/` is a deprecation shim over the external `agent-control-spec` crate. Treat `policy-engine/spec/SPECIFICATION.md` as authoritative.

### 2. Zero-Trust Identity

- 🟢 **AgentIdentity / AgentDID** — Ed25519 keypair, `did:mesh:...` id, `.sign()`/`.verify_signature()`, capability-scoped delegation. `agentmesh.identity.agent_id`.
- 🟢 **Revocation / Rotation** — revoke or rotate agent credentials. `agentmesh.identity.revocation` / `.rotation`.
- 🟡 **Entra / Managed Identity** — enterprise identity backed by Microsoft Entra; needs Azure. `agentmesh.identity.entra`.
- 🟡 **mTLS / SPIFFE** — workload identity in a service mesh; needs PKI/SPIFFE. `agentmesh.identity.mtls` / `.spiffe`.

> Caveat: a locally generated `did:mesh` is random, not key-derived — only registry-issued DIDs are cryptographically bound to a key.

### 3. Trust Scoring (behavioral reputation)

- 🟢 **RewardEngine** — scores agents 0–1000 across five runtime dimensions (policy_compliance, resource_efficiency, output_quality, security_posture, collaboration_health), with tiers, explanations, at-risk list, and automatic revocation below a threshold. `agentmesh.reward.engine.RewardEngine`.
- 🟢 **Trust cards / levels / handshake** — peer-to-peer trust negotiation and verifiable agent cards. `agentmesh.trust.*`.

### 4. Audit & Evidence

- 🟢 **AuditLog + MerkleAuditChain** — hash-chained, tamper-evident record of every decision; `verify_integrity()`, Merkle inclusion proofs, CloudEvents export. `agentmesh.governance.audit.AuditLog`.
- 🟡 **FileAuditSink** — persistent HMAC-signed JSON-lines; needs a ≥32-byte key (`AGT_AUDIT_SECRET_KEY`). `agentmesh.governance.audit_backends.FileAuditSink`.
- 🟡 **CloudEvents / OTLP event sink** — stream governance events to stdout or an OTLP collector. `AuditEntry.to_cloudevent`, `agent_os.event_sink`.
- 🟢 **Decision BOM / audit-compliance spec** — Merkle audit + compliance mapping + Decision BOM contract (157 conformance tests). `docs/specs/AUDIT-COMPLIANCE-1.0.md`, example `examples/decision-bom/`.

### 5. Safety scanners (advisory detectors — not the hard allow/deny boundary)

- 🟢 **Credential redactor** — strip secrets/PII with lookaround-anchored regex. `agent_os.credential_redactor`.
- 🟢 **Prompt injection detector** — heuristic injection detection (embedding variant optional). `agent_os.prompt_injection`.
- 🟢 **PromptDefenseEvaluator** — static A–F grade of a system prompt against OWASP/ASI vectors; deterministic, no LLM, <5ms. `agent-compliance/.../prompt_defense.py`.
- 🟢 **Healthcare identifier detector** — context-cued MRN/NPI/health-plan ID detection (non-mutating; present in Python, Go, .NET, TS). e.g. `agentmesh FindHealthcareIdentifiers`, `HealthcareIdentifierDetector`.

### 6. MCP Security Gateway (tool-poisoning defense)

- 🟢 **MCP Security Scanner** — detects tool poisoning, rug-pull/drift, typosquatting, hidden instructions in MCP tool definitions (ships SAMPLE rules; customize before prod). `agent_os.mcp_security.MCPSecurityScanner`.
- 🟢 **MCP Gateway / Response Scanner** — intercept MCP tool calls + approve/sanitize responses. `agent_os.mcp_gateway`, `.mcp_response_scanner`.
- 🟢 **MCP message signing** — sign/verify MCP envelopes. `agent_os.mcp_message_signer`. Spec: `docs/specs/MCP-SECURITY-GATEWAY-1.0.md` (127 tests).

### 7. Execution Sandboxing & Runtime Control

- 🟠 **Agent Sandbox (five providers)** — execution isolation behind one `SandboxProvider` ABC: `DockerSandboxProvider` (hardened OCI, auto-upgrade gVisor/Kata), `HyperLightSandboxProvider` (micro-VM), `ACASandboxProvider` (Azure Container Apps), `MxcSandboxProvider` (OS-native via MXC binary), `NonoSandboxProvider` (Landlock/Seatbelt kernel sandbox). Public Preview. `agent-governance-python/agent-sandbox/`.
- 🟢 **Hardened sandbox image + deny-shim + AppArmor profile** — pinned-PATH image, execute-bit stripping, logging deny-shim, AppArmor command-denylist. `agent-sandbox/docker/`.
- 🟢 **Execution Rings** — privilege tiers mapped to concrete constraints (network allowlist, fs scope, subprocess, concurrency). `hypervisor.rings.enforcer.RingEnforcer`.
- 🟢 **Command denylist** — structurally block dangerous shell commands. `hypervisor.sandbox` + RingEnforcer.
- 🟢 **Kill Switch** — emergency-terminate an agent with callbacks + in-flight handoff; scoped (global/agent/capability) in the SDKs. `hypervisor.security.kill_switch.KillSwitch`.
- 🟢 **Rate limiter** — cap an agent's action rate. `hypervisor.security.rate_limiter`.
- 🟢 **Delta engine** — hash-chained record of state changes. `hypervisor.audit.delta.DeltaEngine`.
- 🟠 **Reversibility / Saga orchestrator** — multi-step transactions with compensation/rollback (Public Preview). `hypervisor.saga.orchestrator`.
- 🟢 **Agent lifecycle state machine** — eight-state validated transitions (provisioning→active→suspended/rotating/degraded/quarantined→decommissioning→decommissioned); present across SDKs. Spec: `docs/specs/AGENT-HYPERVISOR-EXECUTION-CONTROL-1.0.md` (80 tests).

### 8. SRE / Reliability

- 🟢 **SLO engine + error budgets** — objectives, SLIs, burn-rate alerts, validator. `agent_sre.slo` (`agent-governance-python/agent-sre/`).
- 🟢 **Circuit breaker** — per-agent CLOSED/OPEN/HALF_OPEN to stop cascades. `agent_sre.cascade.circuit_breaker`.
- 🟠 **Chaos / adversarial engine** — fault injection + adversarial playbooks (injection, privilege escalation, exfiltration); powers `agt red-team attack` (Public Preview). `agent_sre.chaos`.
- 🟢 **Cost guardrails, canary/blue-green rollout, anomaly detection** — additional SRE modules present in-tree (`agent-sre/.../cost_guard.py`, `canary_rollout.py`, `blue_green.py`, `anomaly.py`). Spec: `docs/specs/AGENT-SRE-GOVERNANCE-1.0.md` (111 tests).

### 9. Compliance & CLI (`agt`)

- 🟢 **`agt verify`** — OWASP ASI attestation (ASI-01…10), signed, coverage % + A–F grade. `agent_compliance.verify`.
- 🟢 **`agt integrity`** — SHA-256 manifest of governance source + function bytecode ("who watches the watcher"). `agent_compliance.integrity`.
- 🟢 **`agt lint-policy` / `agt test`** — validate policy files; replay test fixtures (exit 1 on mismatch). 
- 🟢 **`agt doctor`** — installation health.
- 🟢 **`agt red-team scan`** — prompt-defense audit over a directory with `--min-grade`.
- 🟡 **`agt cred`** — Fernet-encrypted credential vault (needs `AGT_VAULT_KEY`). `agent_os.credential_vault`.
- 🟡 **SecurityScanner** — secrets/CVE/SAST scan; no-op without detect-secrets/pip-audit/bandit/npm. `agent_compliance.security.scanner`.
- 🟢 **Contributor reputation check** — PR/issue author screening for social engineering; reusable GitHub Action. `agent_compliance/.../contributor_check.py`, `.github/actions/contributor-check/`.

### 10. Discovery, Marketplace, RAG, Learning/RL

- 🟢 **Shadow AI discovery** — inventory agents and flag unregistered ("shadow") ones via process/config scanners; GitHub repo scanner needs a token. `agent-discovery/`.
- 🟢 **Marketplace trust/quality** — score plugins (trust tiers, usage signals, quality) and sign artifacts before install. `agent-marketplace/`.
- 🟢 **RAG governance** — retrieval-time collection access control, rate limiting, chunk content scanning (PII/injection), audit — wraps a LangChain-style retriever. `agent-rag-governance/`.
- 🟡 **RL training governance (Agent Lightning)** — turn policy violations into RL penalties during training. `agent-lightning/` (`agent_lightning_gov`). Spec: `docs/specs/AGENT-LIGHTNING-FAST-PATH-1.0.md` (100 tests).
- 🟠 **Agent Learning governance** — govern Microsoft Agent Learning episode capture, reward shaping, policy promotion/rollout (Public Preview, targets agent-learning 0.8.x). `agent-learning/` (`agent_learning_gov`).

### 11. Framework integrations & HTTP serving

- 🟡 **Framework adapters** — native governance for LangChain/LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Microsoft Agent Framework, Semantic Kernel, Google ADK, LlamaIndex, Haystack, Mastra, Dify, smolagents (needs the target framework). `agent_os.integrations.*`, `agent-governance-python/agentmesh-integrations/`.
- 🟡 **HTTP servers** — `policy_server` (real policy eval over HTTP), `audit_collector`, `trust_engine` (real). Caveat: `policy_server` accepts `agent_did` from the body without authenticating the caller.
- 🟠 **Studio `engine_api`** — policy read/validate/test/save endpoints are real, but `/audit/log`, `/agents`, `/trust/scores`, `/decisions` are placeholder stubs returning empty data. `agentmesh.engine_api`.

### 12. Observability (telemetry emitters)

- 🟡 **OpenTelemetry policy spans** — e.g. Rust `agentmesh.policy.evaluate` spans with sanitized attributes (behind the `telemetry` feature). ACS ships OTel metric sinks across Rust/Python/Node/.NET.
- 🟢 **GovernanceMetrics** — policy-decision counters, latency histograms, trust-score gauges (e.g. .NET `System.Diagnostics.Metrics`, TS `GovernanceMetrics`).
- 🟠 **Governance dashboard (Streamlit demo)** — fed by synthetic data; a UI reference, not a data source. `examples/demos/governance-dashboard/`.

### 13. CI/CD, Supply-chain & Security automation (`.github/`)

Workflows under `.github/workflows/`:
- 🟢 **Supply chain / SBOM / provenance** — `sbom.yml`, `sbom-diff.yml`, `sbom-diff-comment.yml`, `supply-chain-check.yml`, `publish.yml`, `publish-containers.yml`.
- 🟢 **Security scanning** — `codeql.yml` (Python+TS SAST), `secret-scanning.yml` (Gitleaks), `cflite.yml` (ClusterFuzzLite), `scorecard.yml` (OpenSSF), `dependency-review.yml`, `weekly-security-audit.yml`.
- 🟢 **AI-powered governance workflows** — `ai-pr-review.yml`, `ai-owasp-compliance.yml`, `ai-security-scan.yml`, `ai-spec-drafter.yml`, `ai-repo-health.yml`, `ai-contributor-guide.yml`, `ai-release-notes.yml`.
- 🟢 **Quality/governance gates** — `quality-gates.yml`, `policy-validation.yml`, `policy-engine-ci.yml`, `redteam-benchmark.yml`, `benchmarks.yml`, `dco.yml`, `pr-title-check.yml`, `license-check.yml`, `license-headers.yml`, `spell-check.yml`, `docs-quality.yml`, `v4-removal-ratchet.yml`, `contributor-check.yml`.
- 🟢 **Reusable Actions** — `.github/actions/contributor-check/`, `.github/actions/ai-agent-runner/`.
- 🟢 **Root security config** — `.gitleaks.toml` (secret scanning), `.safety.yml`/`.safety-policy.yml` (dependency CVE policy), `.clusterfuzzlite/` (fuzzing harness), `.pre-commit-hooks.yaml`, `.cspell.json`, `Dockerfile`, `docker-compose.yml`.

### 14. Fuzzing & Benchmarks

- 🟢 **ClusterFuzzLite fuzz targets** — 7 targets: policy YAML, condition eval, input validation, MCP security, sandbox, trust scoring, prompt injection. `agent-governance-python/fuzz/`, `.clusterfuzzlite/`.
- 🟢 **Prompt-injection benchmark** — corpus + harness + smoke runner. `benchmarks/prompt-injection/`.

### 15. Schemas, Specs & Docs

- 🟢 **Fixture schema + validator** — `schemas/fixture_schema.json`, `schemas/validate_fixture.py`.
- 🟢 **10 formal RFC-2119 specs with 992 conformance tests** — `docs/specs/` (Policy Engine, ACS, Identity/Trust, Hypervisor, Trust/Coordination, SRE, MCP Gateway, Lightning, Audit/Compliance, Wire protocol).
- 🟢 **29 Architecture Decision Records** — `docs/adr/`.
- 🟢 **Compliance docs** — OWASP ASI architecture, NIST AI RMF, EU AI Act, SOC 2 mapping (docs only; only OWASP ASI is code-enforced). `docs/compliance/`.
- 🟢 **Tutorials, deployment guides, i18n** — `docs/tutorials/`, `docs/deployment/`, `docs/i18n/`, `mkdocs.yml`.

---

## SDKs and CLIs per language / platform

| Platform | Package / path | What it provides |
|---|---|---|
| **Python** | `agent-governance-toolkit[full]` → `agent-governance-python/` | The full stack: policy engine, identity, trust, Merkle audit, MCP security, execution rings/kill-switch/saga, SRE, sandboxing (5 providers), compliance + `agt` CLI, discovery, marketplace, RAG, RL/learning governance, 20+ framework adapters. The only platform with the unified `agt` CLI, OWASP verification, dashboard, and adapters. |
| **TypeScript** | `@microsoft/agent-governance-sdk` → `agent-governance-typescript/` | `AgentMeshClient`, Ed25519 identity, trust, PolicyEngine (+OPA/Cedar backends), hash-chain audit, MCP scanner, lifecycle, rings + kill switch, PromptDefense, GovernanceVerifier, ShadowDiscovery, SRE primitives (metrics/SLO/circuit breaker/trace), generic + WebMCP framework adapters. Also powers the VS Code extension (`agent-os-vscode/`). |
| **.NET** | `Microsoft.AgentGovernance` (+ `.Extensions.ModelContextProtocol`, `.Extensions.Microsoft.Agents`) → `agent-governance-dotnet/` | GovernanceKernel, YAML/JSON policy (+OPA/Cedar), accumulated-context governance, action-bound approval chains, rate limiting, zero-trust identity (ECDSA P-256, not Ed25519 — not key-interchangeable), rings, kill switch, lifecycle, saga, circuit breaker, SLO engine, prompt-injection + prompt-defense + healthcare detectors, shadow discovery, file trust store, OTel metrics, MCP server governance. |
| **Rust** | `agentmesh` + `agentmesh-mcp` → `agent-governance-rust/` | Full governance crate (policy, trust, audit, Ed25519 identity, rings, lifecycle, compliance helpers, kill-switch/SLO, prompt_injection) + standalone MCP crate (signing, session auth, redaction, rate limiting, gateway). Optional `cli` feature exposes a partial operator `agt` binary (`check`/`policy`/`audit`/`trust`); optional `telemetry` feature adds OTel spans. |
| **Go** | `github.com/microsoft/agent-governance-toolkit/agent-governance-golang` | Identity (Ed25519 DID), decay-based trust, rule-based policy (+OPA/Cedar backends), context-accumulation governance, SHA-256 hash-chain audit, MCP scanner, healthcare detector, execution rings, scoped kill switch, 8-state lifecycle, SLO engine, net/http governance middleware (fail-closed), shadow discovery, prompt defense. No framework adapters. |
| **ACS native runtime** | `policy-engine/` (Rust core + Python/Node/.NET/Go bindings) | Language-neutral, stateless, fail-closed policy *decision* runtime: eight lifecycle intervention points, verdicts, transform, IFC label-flow, Rego/Cedar/custom policy types, pluggable telemetry sinks, `acs-generate` CLI (`policy-engine/generator/`). |
| **Claude Code** | `@microsoft/agent-governance-claude-code` | Claude Code plugin: subprocess hooks for `SessionStart` / `UserPromptSubmit` (fail-closed) / `PreToolUse` (allow/deny/ask) + bundled MCP server (`agt_policy_status`, `agt_policy_check_text`). Cannot redact post-tool output. |
| **Codex CLI** | `@microsoft/agent-governance-codex-cli` | OpenAI Codex CLI governance hooks (session/prompt/pre-tool) via a `.codex-plugin` manifest; thin host adapter over the Claude Code governance core. First-party, not yet published to npm. |
| **Copilot CLI** | `@microsoft/agent-governance-copilot-cli` | Installer that deploys a Copilot CLI extension into `~/.copilot`, seeds a default developer-protection policy; lifecycle commands `install`/`update`/`uninstall`/`doctor`. Runs on the TS SDK. |
| **Antigravity CLI** | `@microsoft/agent-governance-antigravity-cli` | Public Preview installer that deploys an extension into `~/.antigravity/`: local MCP server + startup context, prompt/tool/tool-output hooks, `/agt:status` & `/agt:check` commands, seeded policy. |
| **OpenCode** | `@microsoft/agent-governance-opencode` | OpenCode plugin using **in-process** hooks (`tool.execute.before`/`after`) — can enforce without a subprocess round-trip and can **redact** secrets from tool output before the model sees it (a parity win over Claude Code); also ships a stdio MCP server. |
| **GitHub Action** | `action/action.yml` | Reusable GitHub Action surface for running AGT governance/compliance checks in CI. |

---

## How to choose (goal → feature)

- **"I just want to block dangerous tool calls, fast."** → Python `govern()` + a YAML policy + in-memory `AuditLog`. Pure Python, zero deps. (`agent_os.lite.govern` / `agentmesh.governance.govern`)
- **"I need to know which agent did what."** → `AgentIdentity` (Ed25519 DIDs) + Merkle `AuditLog`. (`agentmesh.identity`, `agentmesh.governance.audit`)
- **"I need defensible, tamper-evident evidence for auditors."** → `FileAuditSink` (HMAC-signed) + `agt verify` (OWASP ASI attestation) + `agt integrity`.
- **"My agents run untrusted code / shell."** → `agent-sandbox` providers + Execution Rings + command denylist + Kill Switch.
- **"My agents use third-party MCP tools."** → MCP Security Scanner + Gateway + response scanner + message signing.
- **"I want privileges to adapt to agent behavior."** → `RewardEngine` trust scoring with auto-revocation.
- **"I run a RAG pipeline and need retrieval access control."** → `agent-rag-governance` (`RAGGovernor` / `RAGPolicy`).
- **"I need reliability targets / stop cascading failures."** → `agent-sre` SLO engine + circuit breaker.
- **"I want to find agents running outside governance."** → `agent-discovery` (shadow AI discovery).
- **"I want policy to be language-neutral and formally specified."** → the ACS runtime in `policy-engine/`.
- **"I'm not on Python."** → TS / .NET / Rust / Go SDKs give the four core primitives (policy, identity, trust, audit) + more; reach for Python when you need the `agt` CLI, OWASP verification, dashboard, or framework adapters.
- **"I want governance inside my agent CLI/IDE."** → Claude Code, Codex CLI, Copilot CLI, Antigravity CLI, or OpenCode packages (OpenCode is the only one that can redact tool output in-process).
- **"I want governance enforced in CI."** → `.github/` AI workflows + supply-chain/SBOM/CodeQL/Gitleaks/ClusterFuzzLite + the `action/` GitHub Action + `agt lint-policy`/`agt verify` as gates.

---

## Verification notes (code vs FEATURES.md)

`FEATURES.md` is largely accurate and honest. This inventory confirms its maturity calls and adds the following that `FEATURES.md` under-covers or omits:

- **`agent-sandbox` (5 providers)** — a substantial, Public-Preview execution-isolation subsystem (`agent-governance-python/agent-sandbox/`) not surfaced in the FEATURES.md summary table.
- **`agent-rag-governance`** — retrieval-time governance package, not in FEATURES.md.
- **`agent-learning` governance** — Microsoft Agent Learning integration (separate from Agent Lightning RL), not in FEATURES.md.
- **`agt-policies`** — the v4→v5 policy migration CLI/bridge.
- **ACS verdict-model divergence** — the root README's 5-verdict ACS vs `policy-engine/`'s retargeted closed 3-verdict agent-hooks contract. Use `policy-engine/spec/SPECIFICATION.md` as authoritative.
- **Accumulated-context governance & action-bound approval chains** — fully present in the .NET and Go SDKs (ADR-0030 approval protocol); worth noting as cross-language governance primitives.
- **Confirmed:** the only code-enforced compliance mapping is OWASP ASI; SOC 2 / NIST / EU AI Act are docs + keyword buckets (`agent-compliance/.../cli/contributor_check.py`), not automated checks.
- **Confirmed:** enforcement is middleware-layer (shared process boundary), with per-agent containers recommended for OS isolation (`docs/LIMITATIONS.md`).
