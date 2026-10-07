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

/* Inline icons for the top bar + KPI cards (visual chrome only). */
const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
  </svg>
);
const BellIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 01-3.4 0" />
  </svg>
);
const UsersIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8" />
  </svg>
);
const GaugeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 15l4-4" /><path d="M3 15a9 9 0 1118 0" />
  </svg>
);
const KeyIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="7.5" cy="15.5" r="4.5" /><path d="M10.5 12.5L21 2M17 6l3 3M14 9l2 2" />
  </svg>
);
const PulseIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 12h4l2 7 4-14 2 7h6" />
  </svg>
);

export default function AgentGovernance() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [decisionCount, setDecisionCount] = useState(0);
  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    api.agents().then((r) => setAgents(r.items));
    api.decisions(100).then((r) => setDecisionCount(r.items.length));
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
  const onlinePct = agents.length > 0 ? Math.round((active / agents.length) * 100) : 0;
  const trustPct = Math.round((avgTrust / 1000) * 100);

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>
            Agent <span className="gradient-text">Governance</span>
          </h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Complete, real-time history of every governed agent: identity, decisions, tamper-evident
            audit, trust, and approvals.
          </p>
        </div>
        <div className="topbar-actions">
          <div className="search">
            <SearchIcon />
            <input
              type="text"
              placeholder="Search agents, decisions…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search"
            />
          </div>
          <button className="icon-btn" aria-label="Notifications" type="button">
            <BellIcon />
          </button>
          <div className="avatar-chip">
            <span className="avatar">HS</span>
            <div>
              <div className="avatar-name">Harsh S.</div>
              <div className="avatar-role">Governance admin</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 18 }}>
        <div className="kpi-card kpi-blue">
          <div className="kpi-top">
            <span className="kpi-value">{active}/{agents.length}</span>
            <span className="kpi-ico"><UsersIcon /></span>
          </div>
          <div className="kpi-label">Active Agents</div>
          <div className="kpi-sub">{onlinePct}% online</div>
        </div>

        <div className="kpi-card kpi-green">
          <div className="kpi-top">
            <span className="kpi-value">{avgTrust}<small style={{ fontSize: 14, fontWeight: 600, color: "var(--muted)" }}>/1000</small></span>
            <span className="kpi-ico"><GaugeIcon /></span>
          </div>
          <div className="kpi-label">Average Trust Score</div>
          <div className="trust-bar" style={{ marginTop: 2 }}>
            <div style={{ width: `${trustPct}%` }} />
          </div>
        </div>

        <div className="kpi-card kpi-pink">
          <div className="kpi-top">
            <span className="kpi-value">Ed25519</span>
            <span className="kpi-ico"><KeyIcon /></span>
          </div>
          <div className="kpi-label">Per-agent DID Identity</div>
          <div className="kpi-sub">Decentralized identity for all agents</div>
        </div>

        <div className="kpi-card kpi-amber">
          <div className="kpi-top">
            <span className="kpi-value">{decisionCount}</span>
            <span className="kpi-ico"><PulseIcon /></span>
          </div>
          <div className="kpi-label">Total Decisions Today</div>
          <div className="kpi-sub">Governed policy decisions logged</div>
        </div>
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <AgentRoster agents={agents} onChange={refresh} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 18 }}>
        <DecisionTimeline />
        <ApprovalsQueue onChange={refresh} />
      </div>

      <div className="grid cols-3" style={{ marginBottom: 18 }}>
        <IntakePanel />
        <RagPanel />
        <SecurityPanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <RuntimePanel />
      </div>

      <div className="grid" style={{ marginBottom: 18 }}>
        <AdvisoryPanel />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 18 }}>
        <ShadowDiscoveryPanel />
        <MarketplacePanel />
      </div>

      <div className="grid">
        <AuditTrail refreshKey={refreshKey} />
      </div>
    </div>
  );
}
