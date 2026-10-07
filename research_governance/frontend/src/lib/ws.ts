import { api } from "./api";

export type DecisionHandler = (payload: Record<string, unknown>) => void;

/** Connect to the live decision stream. Returns a close function. */
export function connectDecisions(onEvent: DecisionHandler): () => void {
  const wsUrl = api.base.replace(/^http/, "ws") + "/ws/decisions";
  let ws: WebSocket | null = null;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    ws = new WebSocket(wsUrl);
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data));
      } catch {
        /* ignore malformed */
      }
    };
    ws.onclose = () => {
      if (!closed) retry = setTimeout(open, 1500); // auto-reconnect
    };
    ws.onerror = () => ws?.close();
  };
  open();

  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    ws?.close();
  };
}
