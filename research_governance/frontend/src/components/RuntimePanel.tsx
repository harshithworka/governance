import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { BreakerRow, RingRow, RuntimeEvent } from "../lib/types";

export default function RuntimePanel() {
  const [ringsData, setRings] = useState<RingRow[]>([]);
  const [breakers, setBreakers] = useState<BreakerRow[]>([]);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [egressMsg, setEgressMsg] = useState<string | null>(null);

  const load = () => {
    api.rings().then((r) => setRings(r.items));
    api.breakers().then((r) => setBreakers(r.items));
    api.runtimeEvents(80).then((r) => setEvents(r.items));
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const egress = async () => {
    const r = await api.egressTest("execution", "curl http://evil.example.com");
    setEgressMsg(`${r.allowed ? "ALLOWED" : "BLOCKED"} — ${r.reason}`);
    load();
  };

  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Runtime hardening</h2>
        <button className="ghost" onClick={egress}>
          Simulate egress attempt (curl)
        </button>
      </div>
      {egressMsg && (
        <p className={egressMsg.startsWith("BLOCKED") ? "" : "muted"} style={{ marginTop: 0 }}>
          <span className={`badge ${egressMsg.startsWith("BLOCKED") ? "deny" : "allow"}`}>
            command denylist
          </span>{" "}
          {egressMsg}
        </p>
      )}

      <div className="grid cols-2">
        <div>
          <h2 style={{ fontSize: 13 }}>Execution rings</h2>
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Ring</th>
                <th>Net</th>
                <th>Subproc</th>
              </tr>
            </thead>
            <tbody>
              {ringsData.map((r) => (
                <tr key={r.agent_key}>
                  <td className="mono">{r.agent_key}</td>
                  <td>
                    <span className="pill">{r.ring}</span>
                  </td>
                  <td>{r.network ? "✓" : "—"}</td>
                  <td>{r.subprocess ? "✓" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h2 style={{ fontSize: 13 }}>Circuit breakers</h2>
          {breakers.length === 0 && <p className="muted">No breaker activity yet.</p>}
          <table>
            <tbody>
              {breakers.map((b) => (
                <tr key={b.agent_key}>
                  <td className="mono">{b.agent_key}</td>
                  <td>
                    <span className={`badge ${b.state === "OPEN" ? "deny" : "allow"}`}>
                      {b.state}
                    </span>
                  </td>
                  <td className="muted">
                    {Math.round(b.success_rate * 100)}% ok ({b.slo_success}/{b.slo_total})
                  </td>
                  <td>
                    {b.state === "OPEN" && (
                      <button
                        className="ghost"
                        style={{ padding: "4px 8px", fontSize: 11 }}
                        onClick={() => api.resetBreaker(b.agent_key).then(load)}
                      >
                        reset
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2 style={{ fontSize: 13, marginTop: 16 }}>Runtime events</h2>
      <div style={{ maxHeight: 220, overflow: "auto" }}>
        <table>
          <tbody>
            {events.map((e) => (
              <tr key={e.event_id}>
                <td className="muted mono">{new Date(e.timestamp * 1000).toLocaleTimeString()}</td>
                <td>
                  <span className={`badge ${eventClass(e.kind)}`}>{e.kind}</span>
                </td>
                <td className="muted">{e.agent_name ?? "—"}</td>
                <td className="muted">{e.detail}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No runtime events yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function eventClass(kind: string): string {
  if (kind === "kill" || kind.endsWith("denied") || kind === "breaker_open") return "deny";
  if (kind === "breaker_reset") return "allow";
  return "log";
}
