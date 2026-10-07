import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Agent } from "../lib/types";
import AgentRoster from "../components/AgentRoster";
import DecisionTimeline from "../components/DecisionTimeline";
import AuditTrail from "../components/AuditTrail";
import ApprovalsQueue from "../components/ApprovalsQueue";
import SecurityPanel from "../components/SecurityPanel";
import RuntimePanel from "../components/RuntimePanel";
import AdvisoryPanel from "../components/AdvisoryPanel";
import ShadowDiscoveryPanel from "../components/ShadowDiscoveryPanel";
import MarketplacePanel from "../components/MarketplacePanel";
import IntakePanel from "../components/IntakePanel";
import RagPanel from "../components/RagPanel";

export default function AgentGovernance() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    api.agents().then((r) => setAgents(r.items));
    setRefreshKey((k) => k + 1);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const active = agents.filter((a) => a.status === "active").length;
  const avgTrust =
    agents.length > 0
      ? Math.round(agents.reduce((s, a) => s + a.trust_score, 0) / agents.length)
      : 0;

  return (
    <div>
      <h1>Agent Governance</h1>
      <p className="subtitle">
        Complete, real-time history of every governed agent: identity, decisions, tamper-evident
        audit, trust, and approvals.
      </p>

      <div className="grid cols-3" style={{ marginBottom: 18 }}>
        <div className="panel">
          <div className="metric">
            {active}/{agents.length} <small>agents active</small>
          </div>
        </div>
        <div className="panel">
          <div className="metric">
            {avgTrust} <small>avg trust / 1000</small>
          </div>
        </div>
        <div className="panel">
          <div className="metric">
            Ed25519 <small>per-agent DID identity</small>
          </div>
        </div>
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <AgentRoster agents={agents} onChange={refresh} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 18 }}>
        <DecisionTimeline />
        <ApprovalsQueue onChange={refresh} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 18 }}>
        <IntakePanel />
        <RagPanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <SecurityPanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <RuntimePanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <AdvisoryPanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <ShadowDiscoveryPanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <MarketplacePanel />
      </div>

      <div className="grid">
        <AuditTrail refreshKey={refreshKey} />
      </div>
    </div>
  );
}
