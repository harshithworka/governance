import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ShadowAgent } from "../lib/types";

const RadarIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><path d="M12 12l6-4" />
  </svg>
);

export default function ShadowDiscoveryPanel() {
  const [agents, setAgents] = useState<ShadowAgent[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => api.shadows().then((r) => setAgents(r.items));
  useEffect(() => {
    load();
  }, []);

  const rescan = async () => {
    setBusy(true);
    try {
      const r = await api.discoveryScan();
      setAgents(r.items);
    } finally {
      setBusy(false);
    }
  };

  const shadows = agents.filter((a) => a.status === "shadow");

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><RadarIcon /></span>
          Shadow AI discovery
        </h2>
        <div className="panel-head-actions">
          <span className="panel-meta">
            {shadows.length} shadow · {agents.length - shadows.length} registered
          </span>
          <button className="ghost" onClick={rescan} disabled={busy}>
            {busy ? "Scanning…" : "Re-scan"}
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Agents found running, reconciled against the governed registry. Those with no identity /
        owner are <strong>shadow</strong> (ungoverned) and risk-scored.
      </p>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Type</th>
            <th>Status</th>
            <th>Risk</th>
            <th>Factors / actions</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.fingerprint}>
              <td className="mono">{a.name}</td>
              <td className="muted">{a.agent_type}</td>
              <td>
                <span className={`badge ${a.status === "shadow" ? "deny" : "allow"}`}>
                  {a.status}
                </span>
              </td>
              <td>
                <span className={`badge ${riskClass(a.risk_level)}`}>
                  {a.risk_level} {a.risk_score}
                </span>
              </td>
              <td className="muted cell-wrap" style={{ fontSize: 12 }}>
                {a.status === "shadow"
                  ? (a.recommended[0] ?? a.factors.join("; "))
                  : "governed"}
              </td>
            </tr>
          ))}
          {agents.length === 0 && (
            <tr>
              <td colSpan={5}>
                <div className="empty-state">
                  <span className="empty-ico"><RadarIcon /></span>
                  <p>No discovery results yet. Click "Re-scan".</p>
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function riskClass(level: string): string {
  if (level === "critical" || level === "high") return "deny";
  if (level === "medium") return "require_approval";
  if (level === "low") return "warn";
  return "allow";
}
