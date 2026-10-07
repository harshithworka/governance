import { api } from "../lib/api";
import type { Agent } from "../lib/types";

export default function AgentRoster({
  agents,
  onChange,
}: {
  agents: Agent[];
  onChange: () => void;
}) {
  const act = async (did: string, suspended: boolean) => {
    if (suspended) await api.reactivate(did);
    else await api.kill(did);
    onChange();
  };

  return (
    <div className="panel">
      <h2>Agent roster</h2>
      <div className="grid cols-3">
        {agents.map((a) => {
          const pct = Math.round((a.trust_score / 1000) * 100);
          const suspended = a.status !== "active";
          return (
            <div className="agent-card" key={a.did}>
              <div className="row spread">
                <strong>{a.name}</strong>
                <span className="pill">{a.ring}</span>
              </div>
              <div className="mono muted" style={{ fontSize: 11, margin: "6px 0" }}>
                {a.did.slice(0, 26)}…
              </div>
              <div className="row spread">
                <span>
                  <span className={`status-dot ${a.status}`} />
                  {a.status}
                </span>
                <span className="muted">
                  {a.trust_score}/1000 · {a.trust_tier}
                </span>
              </div>
              <div className="trust-bar">
                <div style={{ width: `${pct}%` }} />
              </div>
              <div className="row spread" style={{ marginTop: 10 }}>
                <span className="muted" style={{ fontSize: 11 }}>
                  {a.capabilities.join(", ")}
                </span>
                <button
                  className={suspended ? "ok" : "danger"}
                  style={{ padding: "5px 10px", fontSize: 12 }}
                  onClick={() => act(a.did, suspended)}
                >
                  {suspended ? "Reactivate" : "Kill"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
