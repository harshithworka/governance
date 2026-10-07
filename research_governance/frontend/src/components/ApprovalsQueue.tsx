import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Approval } from "../lib/types";

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
      <h2>Approvals queue</h2>
      {approvals.length === 0 && <p className="muted">No pending approvals.</p>}
      {approvals.map((a) => (
        <div className="agent-card" key={a.approval_id} style={{ marginBottom: 10 }}>
          <div className="row spread">
            <strong>{a.action}</strong>
            <span className="badge require_approval">pending</span>
          </div>
          <p className="muted" style={{ margin: "6px 0" }}>
            {a.reason}
          </p>
          <div className="mono muted" style={{ fontSize: 12 }}>
            {JSON.stringify(a.payload)}
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
