import { useState } from "react";

import { api } from "../lib/api";

type DemoAction = "mcp" | "agent" | "tamper" | "reset";

export default function Policies() {
  const agents = [
    { name: "Research", rules: "web_search allowed (60/hr); execution/writes/trades denied" },
    { name: "Market-Data", rules: "read data allowed (120/hr); Alpha Vantage 25/day; no execution" },
    { name: "Strategy", rules: "read + draft proposal allowed; execute/approve denied" },
    { name: "Risk Officer", rules: "assess allowed; >250k denied; blocked instruments denied" },
    { name: "Execution", rules: "trades <100k allowed (20/hr); ≥100k require approval; destructive denied" },
  ];

  const [busy, setBusy] = useState<DemoAction | null>(null);
  const [status, setStatus] = useState<string>("");
  const [isError, setIsError] = useState(false);

  async function runDemo(
    action: DemoAction,
    call: () => Promise<Record<string, unknown>>,
    describe: (r: Record<string, unknown>) => string
  ) {
    setBusy(action);
    setStatus("");
    setIsError(false);
    try {
      const res = await call();
      setStatus(describe(res));
      setIsError(false);
    } catch (e) {
      setIsError(true);
      setStatus(`Request failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>
          <span className="gradient-text">Policies</span>
        </h1>
        <p className="subtitle">
          Each agent is governed by its own deterministic YAML policy, loaded into an AGT{" "}
          <span className="mono">PolicyEngine</span>. These are the live rules enforced on every action.
        </p>
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Active rules (summary)</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.name}>
                <td>
                  <strong>{a.name}</strong>
                </td>
                <td className="muted">{a.rules}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── DEMO threat-injection controls (presenter tooling) ───────────── */}
      <div className="panel" style={{ marginTop: 18 }}>
        <div className="panel-head">
          <h2 className="panel-title">
            Demo controls — inject test threats <span className="badge warn">demo</span>
          </h2>
        </div>
        <p className="muted" style={{ marginTop: -4 }}>
          For demonstration: inject threats here, then re-scan on the Agent Governance page to see
          the existing governance detect them. These controls only plant the threat — the detection
          comes from the real scan/vet/verify paths.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 12 }}>
          <button
            disabled={busy !== null}
            onClick={() =>
              runDemo(
                "mcp",
                () => api.addRiskyMcpTool(),
                (r) =>
                  r.ok
                    ? `Injected ${r.tool} — now go to Agent Governance → MCP tool security → ` +
                      `'Re-scan catalog' (shows BLOCKED), and Marketplace vetting → ` +
                      `'Re-vet catalog' (shows REVOKED).`
                    : `Could not inject tool: ${r.error ?? "unknown error"}`
              )
            }
          >
            {busy === "mcp" ? "Injecting…" : "Add risky MCP tool"}
          </button>

          <button
            disabled={busy !== null}
            onClick={() =>
              runDemo(
                "agent",
                () => api.addHarmfulAgent(),
                (r) =>
                  r.ok
                    ? `Injected ${r.agent} — now go to Agent Governance → Shadow AI discovery → ` +
                      `'Re-scan' to see it flagged as a SHADOW / critical agent.`
                    : `Could not inject agent: ${r.error ?? "unknown error"}`
              )
            }
          >
            {busy === "agent" ? "Injecting…" : "Add harmful agent"}
          </button>

          <button
            disabled={busy !== null}
            onClick={() =>
              runDemo(
                "tamper",
                () => api.tamperAudit(),
                (r) =>
                  r.tampered
                    ? `Audit chain corrupted — now go to Agent Governance → Audit trail → ` +
                      `'Verify integrity' to see it flip to FAILED.`
                    : `Nothing tampered: ${r.reason ?? r.error ?? "run a desk cycle first"}`
              )
            }
          >
            {busy === "tamper" ? "Tampering…" : "Tamper with audit log"}
          </button>

          <button
            className="ghost"
            disabled={busy !== null}
            onClick={() =>
              runDemo(
                "reset",
                () => api.resetDemo(),
                (r) =>
                  r.ok
                    ? `Reset complete — injected tools and rogue agents cleared, audit chain ` +
                      `repaired. All panels are back to the clean baseline.`
                    : `Reset failed: ${r.error ?? "unknown error"}`
              )
            }
          >
            {busy === "reset" ? "Resetting…" : "Reset demo threats"}
          </button>
        </div>
        {status && (
          <p className="muted" style={{ marginTop: 12, color: isError ? "var(--deny)" : undefined }}>
            {status}
          </p>
        )}
      </div>
    </div>
  );
}
