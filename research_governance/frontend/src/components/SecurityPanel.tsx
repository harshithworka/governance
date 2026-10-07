import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { McpScan } from "../lib/types";

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
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>MCP tool security</h2>
        <div className="row">
          <span className="muted" style={{ fontSize: 12 }}>
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
              <td colSpan={4} className="muted">
                No scans yet. Click "Re-scan catalog".
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
