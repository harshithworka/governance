export type Verdict = "allow" | "deny" | "warn" | "require_approval" | "log";

export interface Agent {
  did: string;
  name: string;
  role: string;
  status: "active" | "suspended" | "revoked";
  ring: string | null;
  capabilities: string[];
  trust_score: number;
  trust_tier: string;
  last_active: number | null;
  created_at: number;
}

export interface Decision {
  decision_id: string;
  run_id: string | null;
  timestamp: number;
  agent_did: string;
  agent_name: string;
  action: string;
  resource: string | null;
  verdict: Verdict;
  matched_rule: string | null;
  policy_name: string | null;
  reason: string | null;
  latency_ms: number | null;
  kind?: string;
}

export interface AuditEntry {
  entry_id: string;
  timestamp: number;
  agent_did: string;
  action: string;
  outcome: string;
  resource: string | null;
  policy_decision: string | null;
  entry_hash: string | null;
  previous_hash: string | null;
}

export interface Approval {
  approval_id: string;
  run_id: string | null;
  created_at: number;
  agent_did: string;
  action: string;
  reason: string | null;
  payload: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
}

export interface TrustPoint {
  timestamp: number;
  trust_score: number;
  trust_tier: string | null;
}

export interface McpThreat {
  type: string;
  severity: string;
  message: string;
  tool: string;
  server: string;
}

export interface McpScan {
  scan_id: string;
  timestamp: number;
  server: string;
  tool_name: string;
  safe: boolean;
  allowed: boolean;
  threat_count: number;
  max_severity: string | null;
  threats: McpThreat[];
  demo_malicious: boolean;
}

export interface RingRow {
  agent_key: string;
  ring: string;
  ring_level: number;
  network: boolean;
  filesystem: string;
  subprocess: boolean;
  max_concurrent_tools: number;
}

export interface BreakerRow {
  agent_key: string;
  state: string;
  failures: number;
  slo_total: number;
  slo_success: number;
  success_rate: number;
}

export interface RuntimeEvent {
  event_id: string;
  timestamp: number;
  agent_name: string | null;
  kind: string;
  detail: string | null;
  data: Record<string, unknown>;
}

export interface KillRecord {
  kill_id: string;
  agent_did: string;
  reason: string;
  terminated: boolean;
  timestamp: string;
}

export interface AdvisoryDecision {
  decision_id: string;
  timestamp: number;
  agent_name: string;
  action: string;
  verdict: Verdict;
  reason: string | null;
  advisory_action: string | null;
  advisory_confidence: number | null;
  advisory_reason: string | null;
  advisory_classifier: string | null;
}

export interface ShadowAgent {
  fingerprint: string;
  name: string;
  agent_type: string;
  status: string;
  did: string | null;
  owner: string | null;
  confidence: number;
  risk_level: string;
  risk_score: number;
  factors: string[];
  recommended: string[];
}

export interface PluginVetting {
  tool_name: string;
  server: string;
  trust_score: number;
  tier: string;
  quality_grade: string;
  quality_score: number;
  signed: boolean;
  verified: boolean;
  allowed: boolean;
  notes: string;
}

export interface Redaction {
  type: string;
  value: string;
}

export interface IntakeResult {
  ok: boolean;
  original_len: number;
  clean_query: string;
  redactions: Redaction[];
  injection_detected: boolean;
  injection_threat: string;
  injection_reason: string;
  injection_patterns: string[];
  company: string | null;
  symbol: string | null;
  block_reason: string | null;
}

export interface IntakeEvent extends IntakeResult {
  intake_id: string;
  timestamp: number;
}

export interface RagRetrieval {
  retrieval_id: string;
  timestamp: number;
  run_id: string | null;
  symbol: string;
  source: string;
  report_url: string | null;
  chunks_total: number;
  chunks_used: number;
  chunks_flagged: number;
  available: boolean;
  reason: string;
}

export interface RunResult {
  run_id: string;
  status: string;
  blocked_by: string | null;
  approval_id: string | null;
  result: Record<string, unknown> | null;
  proposal: Record<string, unknown> | null;
  rag: Record<string, unknown> | null;
  trace: Array<Record<string, unknown>>;
}
