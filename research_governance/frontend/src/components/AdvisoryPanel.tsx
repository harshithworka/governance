import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AdvisoryDecision } from "../lib/types";

export default function AdvisoryPanel() {
  const [items, setItems] = useState<AdvisoryDecision[]>([]);

  const load = () => api.advisory().then((r) => setItems(r.items));
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const blocked = items.filter((i) => i.advisory_action === "block").length;
  const flagged = items.filter((i) => i.advisory_action === "flag_for_review").length;

  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Advisory layer (non-deterministic)</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {blocked} blocked · {flagged} flagged
        </span>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        A probabilistic classifier runs <strong>after</strong> the deterministic allow and can only
        tighten it — flagging or blocking a suspicious-but-permitted trade. It never loosens a deny.
        (Swap the heuristic for a System-1 decision model to go live.)
      </p>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Advisory</th>
            <th>Confidence</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.decision_id}>
              <td className="muted mono">{new Date(d.timestamp * 1000).toLocaleTimeString()}</td>
              <td className="mono">{d.action}</td>
              <td>
                <span
                  className={`badge ${d.advisory_action === "block" ? "deny" : "require_approval"}`}
                >
                  {d.advisory_action}
                </span>
              </td>
              <td className="muted">
                {d.advisory_confidence != null ? `${Math.round(d.advisory_confidence * 100)}%` : "—"}
              </td>
              <td className="muted">{d.advisory_reason}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No advisory flags yet. Try a large trade with negative sentiment (e.g. a watchlist
                ticker) to trigger one.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
