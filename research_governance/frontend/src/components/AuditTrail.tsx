import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AuditEntry } from "../lib/types";

const LockIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="11" width="16" height="9" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" />
  </svg>
);

export default function AuditTrail({ refreshKey }: { refreshKey: number }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verify, setVerify] = useState<{ ok: boolean; error: string | null } | null>(null);

  useEffect(() => {
    api.audit(200).then((r) => setEntries(r.items));
  }, [refreshKey]);

  const doVerify = async () => setVerify(await api.verifyAudit());

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><LockIcon /></span>
          Tamper-evident audit trail
        </h2>
        <div className="panel-head-actions">
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
                <td colSpan={4}>
                  <div className="empty-state">
                    <span className="empty-ico"><LockIcon /></span>
                    <p>No audit entries yet.</p>
                  </div>
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
