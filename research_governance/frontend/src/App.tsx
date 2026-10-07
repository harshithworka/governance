import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import Desk from "./pages/Desk";
import AgentGovernance from "./pages/AgentGovernance";
import Policies from "./pages/Policies";

export default function App() {
  const [mode, setMode] = useState<string>("…");

  useEffect(() => {
    api.health().then((h) => setMode(h.mode)).catch(() => setMode("offline"));
  }, []);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          GovDesk
          <small>Governed financial desk</small>
        </div>
        <nav className="nav">
          <NavLink to="/desk" className={({ isActive }) => (isActive ? "active" : "")}>
            Desk
          </NavLink>
          <NavLink to="/governance" className={({ isActive }) => (isActive ? "active" : "")}>
            Agent Governance
          </NavLink>
          <NavLink to="/policies" className={({ isActive }) => (isActive ? "active" : "")}>
            Policies
          </NavLink>
        </nav>
        <div className="mode-badge">
          backend: <strong>{mode}</strong>
          <br />
          {mode === "mock" ? "no API keys — deterministic demo" : "live providers enabled"}
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
