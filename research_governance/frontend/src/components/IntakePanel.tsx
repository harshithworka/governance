import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { IntakeEvent } from "../lib/types";

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
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Governed intake</h2>
        <span className="muted" style={{ fontSize: 12 }}>
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
              <td className="muted" style={{ maxWidth: 240 }}>{e.clean_query}</td>
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
              <td colSpan={5} className="muted">No intake events yet. Submit a request on the Desk page.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
