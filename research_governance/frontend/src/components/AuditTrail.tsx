import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AuditEntry } from "../lib/types";

export default function AuditTrail({ refreshKey }: { refreshKey: number }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verify, setVerify] = useState<{ ok: boolean; error: string | null } | null>(null);

  useEffect(() => {
    api.audit(200).then((r) => setEntries(r.items));
  }, [refreshKey]);

  const doVerify = async () => setVerify(await api.verifyAudit());

  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Tamper-evident audit trail</h2>
        <div className="row">
          {verify && (
            <span className={`badge ${verify.ok ? "allow" : "deny"}`}>
              {verify.ok ? "chain verified ✓" : "FAILED"}
            </span>
          )}
          <button className="ghost" onClick={doVerify}>
            Verify integrity
          </button>
        </div>
      </div>
      <div style={{ maxHeight: 320, overflow: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Outcome</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.entry_id}>
                <td className="muted mono">{new Date(e.timestamp * 1000).toLocaleTimeString()}</td>
                <td className="mono">{e.action}</td>
                <td>
                  <span className={`badge ${outcomeClass(e.outcome)}`}>{e.outcome}</span>
                </td>
                <td className="mono muted">{(e.entry_hash ?? "").slice(0, 14)}…</td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No audit entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function outcomeClass(o: string): string {
  if (o === "success") return "allow";
  if (o === "denied" || o === "deny") return "deny";
  if (o === "require_approval") return "require_approval";
  return "log";
}
