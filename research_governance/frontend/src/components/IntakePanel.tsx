import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { IntakeEvent } from "../lib/types";

const FilterIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 5h18l-7 8v6l-4 2v-8L3 5z" />
  </svg>
);

export default function IntakePanel() {
  const [events, setEvents] = useState<IntakeEvent[]>([]);

  const load = () => api.intakeEventsList().then((r) => setEvents(r.items));
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const blocked = events.filter((e) => !e.ok).length;
  const redactedTotal = events.reduce((s, e) => s + e.redactions.length, 0);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><FilterIcon /></span>
          Governed intake
        </h2>
        <span className="panel-meta">
          {blocked} blocked · {redactedTotal} PII item(s) redacted
        </span>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Each user request is PII-redacted and scanned for prompt injection before any agent runs.
        A detected injection blocks the request.
      </p>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Query</th>
            <th>Injection</th>
            <th>PII</th>
            <th>Symbol</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.intake_id}>
              <td className="muted mono">{new Date(e.timestamp * 1000).toLocaleTimeString()}</td>
              <td className="muted cell-truncate" title={e.clean_query}>{e.clean_query}</td>
              <td>
                <span className={`badge ${e.injection_detected ? "deny" : "allow"}`}>
                  {e.injection_detected ? e.injection_threat : "clean"}
                </span>
              </td>
              <td className="muted">{e.redactions.length}</td>
              <td className="mono">{e.ok ? (e.symbol ?? "—") : "blocked"}</td>
            </tr>
          ))}
          {events.length === 0 && (
            <tr>
              <td colSpan={5}>
                <div className="empty-state">
                  <span className="empty-ico"><FilterIcon /></span>
                  <p>No intake events yet. Submit a request on the Desk page.</p>
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
