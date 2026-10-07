import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { RagRetrieval } from "../lib/types";

const BookIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 5a2 2 0 012-2h7v18H6a2 2 0 00-2 2V5z" /><path d="M13 3h5a2 2 0 012 2v16a2 2 0 00-2-2h-5" />
  </svg>
);

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
      <div className="panel-head">
        <h2 className="panel-title">
          <span className="panel-ico"><BookIcon /></span>
          Annual-report RAG
        </h2>
        <span className="panel-meta">
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
              <td colSpan={6}>
                <div className="empty-state">
                  <span className="empty-ico"><BookIcon /></span>
                  <p>No retrievals yet. Run a desk cycle.</p>
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
