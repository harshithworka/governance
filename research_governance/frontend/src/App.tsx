import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import Desk from "./pages/Desk";
import AgentGovernance from "./pages/AgentGovernance";
import Policies from "./pages/Policies";

/* Minimal inline icon set (visual chrome only). */
const icons: Record<string, ReactNode> = {
  desk: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" />
    </svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
    </svg>
  ),
  policy: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 3h8l3 3v15H5V3h3z" /><path d="M9 9h6M9 13h6M9 17h4" />
    </svg>
  ),
};

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "active" : "";
}

export default function App() {
  const [mode, setMode] = useState<string>("…");

  useEffect(() => {
    api.health().then((h) => setMode(h.mode)).catch(() => setMode("offline"));
  }, []);

  const isMock = mode === "mock";

  return (
    <div className="app">
      <aside className="sidebar">
        <div>
          <div className="brand">
            <span className="brand-mark">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round">
                <path d="M12 2l9 5v6c0 5-4 8-9 9-5-1-9-4-9-9V7l9-5z" />
              </svg>
            </span>
            GovDesk
          </div>
          <small>Governed financial desk</small>

          <nav className="nav">
            <NavLink to="/desk" className={navClass}>
              <span className="nav-icon">{icons.desk}</span> Desk
            </NavLink>
            <NavLink to="/governance" className={navClass}>
              <span className="nav-icon">{icons.shield}</span> Agent Governance
            </NavLink>
            <NavLink to="/policies" className={navClass}>
              <span className="nav-icon">{icons.policy}</span> Policies
            </NavLink>
          </nav>
        </div>

        <div className="mode-badge">
          <div className="mode-head">
            <span className="mode-dot" /> Backend: {isMock ? "Mock" : "Live"}
          </div>
          <div className="mode-sub">
            {isMock ? "no API keys — deterministic demo" : "Live providers enabled"}
          </div>
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/governance" replace />} />
          <Route path="/desk" element={<Desk />} />
          <Route path="/governance" element={<AgentGovernance />} />
          <Route path="/policies" element={<Policies />} />
        </Routes>
      </main>
    </div>
  );
}
