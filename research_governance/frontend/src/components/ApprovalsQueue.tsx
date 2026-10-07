import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Approval } from "../lib/types";

const InboxIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.5 5h13l3.5 7v7a2 2 0 01-2 2H4a2 2 0 01-2-2v-7l3.5-7z" />
  </svg>
);

export default function ApprovalsQueue({ onChange }: { onChange: () => void }) {
  const [approvals, setApprovals] = useState<Approval[]>([]);

  const load = () => api.approvals("pending").then((r) => setApprovals(r.items));
  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  const resolve = async (id: string, approved: boolean) => {
    await api.resolveApproval(id, approved);
    await load();
    onChange();
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><InboxIcon /></span>
          Approvals queue
        </h2>
      </div>
      {approvals.length === 0 && (
        <div className="empty-state">
          <span className="empty-ico"><InboxIcon /></span>
          <p>No pending approvals. Trades that need sign-off will show up here.</p>
        </div>
      )}
      {approvals.map((a) => (
        <div className="agent-card" key={a.approval_id} style={{ marginBottom: 10 }}>
          <div className="row spread">
            <strong>{a.action}</strong>
            <span className="badge require_approval">pending</span>
          </div>
          <p className="muted" style={{ margin: "6px 0" }}>
            {a.reason}
          </p>
          <div className="kv-list">
            {Object.entries(a.payload).map(([k, v]) => (
              <div className="kv-row" key={k}>
                <span className="kv-key" title={k}>{k}</span>
                <span className="kv-val">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10, gap: 8 }}>
            <button className="ok" onClick={() => resolve(a.approval_id, true)}>
              Approve
            </button>
            <button className="danger" onClick={() => resolve(a.approval_id, false)}>
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
