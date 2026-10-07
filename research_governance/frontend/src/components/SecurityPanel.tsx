import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { McpScan } from "../lib/types";

const ShieldIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" />
  </svg>
);

export default function SecurityPanel() {
  const [scans, setScans] = useState<McpScan[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => api.mcpScans().then((r) => setScans(r.items));
  useEffect(() => {
    load();
  }, []);

  const rescan = async () => {
    setBusy(true);
    try {
      const r = await api.mcpRescan();
      setScans(r.items);
    } finally {
      setBusy(false);
    }
  };

  const blocked = scans.filter((s) => !s.allowed).length;
  const flagged = scans.filter((s) => !s.safe).length;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><ShieldIcon /></span>
          MCP tool security
        </h2>
        <div className="panel-head-actions">
          <span className="panel-meta">
            {blocked} blocked · {flagged} flagged · {scans.length} tools
          </span>
          <button className="ghost" onClick={rescan} disabled={busy}>
            {busy ? "Scanning…" : "Re-scan catalog"}
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Every market-data tool is screened for poisoning, hidden instructions, typosquatting and
        rug-pulls before the Market-Data agent may use it. A critical finding blocks the tool.
      </p>
      <table>
        <thead>
          <tr>
            <th>Tool</th>
            <th>Server</th>
            <th>Status</th>
            <th>Threats</th>
          </tr>
        </thead>
        <tbody>
          {scans.map((s) => (
            <tr key={s.scan_id}>
              <td className="mono">
                {s.tool_name}
                {s.demo_malicious && (
                  <span className="pill" style={{ marginLeft: 6 }}>
                    demo-malicious
                  </span>
                )}
              </td>
              <td className="muted">{s.server}</td>
              <td>
                {!s.allowed ? (
                  <span className="badge deny">blocked</span>
                ) : s.safe ? (
                  <span className="badge allow">clean</span>
                ) : (
                  <span className="badge require_approval">flagged</span>
                )}
              </td>
              <td className="muted">
                {s.threat_count === 0 ? (
                  "—"
                ) : (
                  <span title={s.threats.map((t) => `${t.severity}: ${t.message}`).join("\n")}>
                    {s.threat_count} ({s.max_severity})
                  </span>
                )}
              </td>
            </tr>
          ))}
          {scans.length === 0 && (
            <tr>
              <td colSpan={4}>
                <div className="empty-state">
                  <span className="empty-ico"><ShieldIcon /></span>
                  <p>No scans yet. Click "Re-scan catalog".</p>
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
