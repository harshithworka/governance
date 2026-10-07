import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { connectDecisions } from "../lib/ws";
import type { Decision } from "../lib/types";

const TimelineIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
  </svg>
);

export default function DecisionTimeline() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [live, setLive] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    api.decisions(100).then((r) => {
      r.items.forEach((d) => seen.current.add(d.decision_id));
      setDecisions(r.items);
    });
    const close = connectDecisions((payload) => {
      if (payload.kind !== "decision") return;
      const d = payload as unknown as Decision;
      if (seen.current.has(d.decision_id)) return;
      seen.current.add(d.decision_id);
      setLive(true);
      setDecisions((prev) => [d, ...prev].slice(0, 200));
    });
    return close;
  }, []);

  const shown = decisions.filter((d) => filter === "all" || d.verdict === filter);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><TimelineIcon /></span>
          Decision timeline {live && <span className="live-dot" title="live" />}
        </h2>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">all verdicts</option>
          <option value="allow">allow</option>
          <option value="deny">deny</option>
          <option value="require_approval">require_approval</option>
        </select>
      </div>
      <div style={{ maxHeight: 420, overflow: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Agent</th>
              <th>Action</th>
              <th>Verdict</th>
              <th>Rule</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => (
              <tr key={d.decision_id}>
                <td className="muted mono">{fmt(d.timestamp)}</td>
                <td>{d.agent_name}</td>
                <td className="mono">{d.action}</td>
                <td>
                  <span className={`badge ${d.verdict}`}>{d.verdict}</span>
                </td>
                <td className="muted cell-truncate" title={d.matched_rule ?? undefined}>
                  {d.matched_rule ?? "—"}
                </td>
                <td className="muted">{d.latency_ms != null ? `${d.latency_ms}ms` : "—"}</td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <span className="empty-ico"><TimelineIcon /></span>
                    <p>No decisions yet. Run a cycle on the Desk page.</p>
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

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}
