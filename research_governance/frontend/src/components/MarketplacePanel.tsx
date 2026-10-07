import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { PluginVetting } from "../lib/types";

export default function MarketplacePanel() {
  const [items, setItems] = useState<PluginVetting[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => api.marketplace().then((r) => setItems(r.items));
  useEffect(() => {
    load();
  }, []);

  const vet = async () => {
    setBusy(true);
    try {
      const r = await api.marketplaceVet();
      setItems(r.items);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Marketplace vetting</h2>
        <button className="ghost" onClick={vet} disabled={busy}>
          {busy ? "Vetting…" : "Re-vet catalog"}
        </button>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Each MCP data tool is vetted as a signed plugin: Ed25519 signature, trust tier, and quality
        grade. A tool blocked by the MCP security scan is forced to the <strong>revoked</strong>{" "}
        tier — it cannot be trusted through the marketplace either.
      </p>
      <table>
        <thead>
          <tr>
            <th>Tool</th>
            <th>Tier</th>
            <th>Score</th>
            <th>Grade</th>
            <th>Signed</th>
            <th>Allowed</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.tool_name}>
              <td className="mono">{p.tool_name}</td>
              <td>
                <span className={`badge ${tierClass(p.tier)}`}>{p.tier}</span>
              </td>
              <td className="muted">{p.trust_score}</td>
              <td className="muted">{p.quality_grade}</td>
              <td>{p.signed && p.verified ? "✓" : "—"}</td>
              <td>
                {p.allowed ? (
                  <span className="badge allow">yes</span>
                ) : (
                  <span className="badge deny">no</span>
                )}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No vettings yet. Click "Re-vet catalog".
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function tierClass(tier: string): string {
  if (tier === "revoked") return "deny";
  if (tier === "probationary") return "require_approval";
  if (tier === "verified" || tier === "trusted") return "allow";
  return "log";
}
