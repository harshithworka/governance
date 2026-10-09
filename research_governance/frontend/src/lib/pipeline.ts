import { api } from "./api";
import type { PipelineEvent } from "./types";

export type PipelineHandler = (event: PipelineEvent) => void;

/**
 * Open the sequential-pipeline SSE stream for one desk run.
 *
 * EventSource is GET-only, so run parameters are passed in the query string.
 * Each `message` is a JSON `PipelineEvent`. The caller receives every parsed
 * event; it should close the stream (via the returned fn) on WORKFLOW_COMPLETED
 * / WORKFLOW_BLOCKED and on component unmount.
 *
 * Returns a close function.
 */
export function connectPipeline(
  params: { symbol: string; amount: number; query?: string },
  onEvent: PipelineHandler,
  onError?: (err: Event) => void
): () => void {
  const qs = new URLSearchParams({
    symbol: params.symbol,
    amount: String(params.amount),
  });
  if (params.query) qs.set("query", params.query);

  const url = `${api.base}/api/desk/run-stream?${qs.toString()}`;
  const es = new EventSource(url);
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
  };

  es.onmessage = (ev) => {
    try {
      const event = JSON.parse(ev.data) as PipelineEvent;
      onEvent(event);
      if (
        event.type === "WORKFLOW_COMPLETED" ||
        event.type === "WORKFLOW_BLOCKED"
      ) {
        close();
      }
    } catch {
      /* ignore malformed frames */
    }
  };

  es.onerror = (err) => {
    // EventSource auto-reconnects by default; for a one-shot run we don't want
    // that. If the stream already finished we've closed it; otherwise surface
    // the error and stop.
    if (!closed) {
      onError?.(err);
      close();
    }
  };

  return close;
}
