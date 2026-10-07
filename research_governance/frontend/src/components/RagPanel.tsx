import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { RagRetrieval } from "../lib/types";

export default function RagPanel() {
  const [items, setItems] = useState<RagRetrieval[]>([]);

  const load = () => api.ragRetrievals().then((r) => setItems(r.items));
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const flaggedTotal = items.reduce((s, i) => s + i.chunks_flagged, 0);

  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Annual-report RAG</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {flaggedTotal} chunk(s) flagged for injection
        </span>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        The Market-Data agent grounds analysis in each company's NSE annual report. Retrieved
        passages are screened for indirect prompt injection before reaching the LLM.
      </p>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>Source</th>
            <th>Chunks used</th>
            <th>Flagged</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.retrieval_id}>
              <td className="muted mono">{new Date(r.timestamp * 1000).toLocaleTimeString()}</td>
              <td className="mono">{r.symbol}</td>
              <td className="muted">{r.source}</td>
              <td className="muted">{r.chunks_used}</td>
              <td>
                {r.chunks_flagged > 0 ? (
                  <span className="badge deny">{r.chunks_flagged}</span>
                ) : (
                  <span className="muted">0</span>
                )}
              </td>
              <td>
                <span className={`badge ${r.available ? "allow" : "log"}`}>
                  {r.available ? "grounded" : "no report"}
                </span>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">No retrievals yet. Run a desk cycle.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
