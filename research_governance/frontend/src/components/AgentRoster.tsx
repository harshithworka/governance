import { api } from "../lib/api";
import type { Agent } from "../lib/types";

const AgentIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="8" width="16" height="12" rx="2" /><path d="M12 8V4M8 4h8" />
    <circle cx="9" cy="14" r="1" /><circle cx="15" cy="14" r="1" />
  </svg>
);

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
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><AgentIcon /></span>
          Agent roster
        </h2>
        <span className="panel-meta">{agents.length} agent(s)</span>
      </div>
      <div className="grid cols-3">
        {agents.map((a) => {
          const pct = Math.round((a.trust_score / 1000) * 100);
          const suspended = a.status !== "active";
          return (
            <div className="agent-card" key={a.did}>
              <div className="row spread">
                <div className="row" style={{ gap: 10 }}>
                  <span className="agent-ico"><AgentIcon /></span>
                  <strong>{a.name}</strong>
                </div>
                <span className="pill">{a.ring}</span>
              </div>
              <div className="mono muted" style={{ fontSize: 11, margin: "10px 0" }}>
                {a.did.slice(0, 26)}…
              </div>
              <div className="row spread">
                <span style={{ display: "inline-flex", alignItems: "center" }}>
                  <span className={`status-dot ${a.status}`} />
                  {a.status}
                </span>
                <span className="muted" style={{ textAlign: "right" }}>
                  <strong style={{ color: "var(--text)" }}>{a.trust_score}</strong>/1000 · {a.trust_tier}
                </span>
              </div>
              <div className="trust-bar">
                <div style={{ width: `${pct}%` }} />
              </div>
              <div className="row spread" style={{ marginTop: 12 }}>
                <span style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {a.capabilities.map((c) => (
                    <span key={c} className="pill" style={{ fontSize: 10 }}>
                      {c}
                    </span>
                  ))}
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
