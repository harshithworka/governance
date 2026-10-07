import type {
  AdvisoryDecision,
  Agent,
  Approval,
  AuditEntry,
  BreakerRow,
  Decision,
  IntakeEvent,
  IntakeResult,
  KillRecord,
  McpScan,
  PluginVetting,
  RagRetrieval,
  RingRow,
  RunResult,
  RuntimeEvent,
  ShadowAgent,
  TrustPoint,
} from "./types";

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

export const api = {
  base: BASE,
  health: () => get<{ status: string; mode: string }>("/api/health"),
  capabilities: () =>
    get<{ llm: boolean; research: boolean; market_data: boolean; mode: string }>(
      "/api/desk/capabilities"
    ),
  intake: (query: string) => post<IntakeResult>("/api/desk/intake", { query }),
  runDesk: (symbol: string, amount: number, query?: string) =>
    post<RunResult>("/api/desk/run", { symbol, amount, query }),

  agents: () => get<{ items: Agent[] }>("/api/governance/agents"),
  decisions: (limit = 100) =>
    get<{ items: Decision[] }>(`/api/governance/decisions?limit=${limit}`),
  audit: (limit = 200) => get<{ items: AuditEntry[] }>(`/api/governance/audit?limit=${limit}`),
  verifyAudit: () => get<{ ok: boolean; error: string | null }>("/api/governance/audit/verify"),
  trust: (did: string) =>
    get<{ agent_did: string; items: TrustPoint[] }>(
      `/api/governance/trust/${encodeURIComponent(did)}`
    ),
  kill: (did: string) => post(`/api/governance/kill/${encodeURIComponent(did)}`),
  reactivate: (did: string) => post(`/api/governance/reactivate/${encodeURIComponent(did)}`),

  approvals: (status?: string) =>
    get<{ items: Approval[] }>(`/api/approvals${status ? `?status=${status}` : ""}`),
  resolveApproval: (id: string, approved: boolean) =>
    post<{ approval_id: string; status: string; result: unknown }>(
      `/api/approvals/${id}/resolve`,
      { approved }
    ),

  mcpScans: () => get<{ items: McpScan[] }>("/api/governance/mcp/scans"),
  mcpRescan: () => post<{ scanned: number; items: McpScan[] }>("/api/governance/mcp/scan"),

  rings: () => get<{ items: RingRow[] }>("/api/governance/rings"),
  breakers: () => get<{ items: BreakerRow[] }>("/api/governance/breakers"),
  resetBreaker: (key: string) => post(`/api/governance/breakers/${key}/reset`),
  kills: () => get<{ items: KillRecord[] }>("/api/governance/kills"),
  runtimeEvents: (limit = 100) =>
    get<{ items: RuntimeEvent[] }>(`/api/governance/runtime/events?limit=${limit}`),
  egressTest: (key: string, command: string) =>
    post<{ agent: string; command: string; allowed: boolean; reason: string }>(
      `/api/governance/runtime/egress-test/${key}?command=${encodeURIComponent(command)}`
    ),

  advisory: () => get<{ items: AdvisoryDecision[] }>("/api/governance/advisory"),

  intakeEventsList: () => get<{ items: IntakeEvent[] }>("/api/governance/intake"),
  ragRetrievals: () => get<{ items: RagRetrieval[] }>("/api/governance/rag"),

  shadows: () => get<{ items: ShadowAgent[] }>("/api/governance/discovery/shadows"),
  discoveryScan: () =>
    post<{ summary: Record<string, number>; items: ShadowAgent[] }>(
      "/api/governance/discovery/scan"
    ),
  marketplace: () => get<{ items: PluginVetting[] }>("/api/governance/marketplace"),
  marketplaceVet: () =>
    post<{ vetted: number; items: PluginVetting[] }>("/api/governance/marketplace/vet"),
};
