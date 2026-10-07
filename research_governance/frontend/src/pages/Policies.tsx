export default function Policies() {
  const agents = [
    { name: "Research", rules: "web_search allowed (60/hr); execution/writes/trades denied" },
    { name: "Market-Data", rules: "read data allowed (120/hr); Alpha Vantage 25/day; no execution" },
    { name: "Strategy", rules: "read + draft proposal allowed; execute/approve denied" },
    { name: "Risk Officer", rules: "assess allowed; >250k denied; blocked instruments denied" },
    { name: "Execution", rules: "trades <100k allowed (20/hr); ≥100k require approval; destructive denied" },
  ];
  return (
    <div>
      <h1>Policies</h1>
      <p className="subtitle">
        Each agent is governed by its own deterministic YAML policy, loaded into an AGT{" "}
        <span className="mono">PolicyEngine</span>. These are the live rules enforced on every action.
      </p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Active rules (summary)</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.name}>
                <td>
                  <strong>{a.name}</strong>
                </td>
                <td className="muted">{a.rules}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ marginTop: 14 }}>
        Policy files live in <span className="mono">backend/app/policies/*.yaml</span>. Edit and restart
        the backend to change enforcement.
      </p>
    </div>
  );
}
