"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
    : "ws://localhost:8000");

export type LogEvent = {
  type: "log" | "status" | "job_update" | "download_update";
  data: any;
};

type ConnState = "connecting" | "live" | "polling" | "offline";

/**
 * Polling fallback for browsers (e.g. Cursor's built-in webview) that
 * silently drop WebSocket connections to localhost. Always runs alongside
 * WS — when WS is alive we de-duplicate by id at the source; when WS is
 * dead the polling loop is the only path that delivers events.
 *
 * Returns a ref-like object whose `current.resetCursor()` method forces
 * the next poll to start from the beginning (id 0) instead of resuming
 * from the last seen id.
 */
export function usePollingSystemEvents(onEvent?: (e: LogEvent) => void) {
  const sinceRef = useRef(0);
  const cancelledRef = useRef(false);
  const inFlightRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    let intervalId: number | null = null;

    const tick = async () => {
      if (cancelledRef.current || inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const { data } = await api.get("/api/logs/system", {
          params: { since: sinceRef.current, limit: 200 },
        });
        if (cancelledRef.current) return;
        sinceRef.current = data.latest ?? sinceRef.current;
        for (const ev of data.events ?? []) {
          if (ev.type === "log") {
            onEvent?.({
              type: "log",
              data: {
                job_id: ev.job_id,
                level: ev.level,
                message: ev.message,
              },
            } as LogEvent);
          } else {
            // job_update, download_update, status — re-emit as-is
            onEvent?.(ev as LogEvent);
          }
        }
      } catch {
        /* ignore — next tick will retry */
      } finally {
        inFlightRef.current = false;
      }
    };

    // Fire once immediately so the panel isn't empty on first paint.
    tick();
    intervalId = window.setInterval(tick, 1000);
    return () => {
      cancelledRef.current = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    resetCursor: () => {
      sinceRef.current = 0;
    },
  };
}

export function useJobWebSocket(jobId: number | null, onEvent?: (e: LogEvent) => void) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) {
      setConnected(false);
      return;
    }

    function connect() {
      const url = `${WS_BASE}/ws/jobs/${jobId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        reconnectRef.current = window.setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (msg) => {
        try {
          const parsed: LogEvent = JSON.parse(msg.data);
          onEvent?.(parsed);
        } catch {
          /* ignore */
        }
      };
    }

    connect();
    return () => {
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return { connected };
}

export function useSystemWebSocket(onEvent?: (e: LogEvent) => void) {
  const [connected, setConnected] = useState<ConnState>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const fallbackTimer = useRef<number | null>(null);
  const fallbackActivated = useRef(false);

  // Always run polling in parallel — guarantees the panel gets events even
  // if the browser refuses to open a WebSocket.
  const polling = usePollingSystemEvents(onEvent);

  useEffect(() => {
    function connect() {
      if (fallbackActivated.current) return;
      try {
        const ws = new WebSocket(`${WS_BASE}/ws/system`);
        wsRef.current = ws;
        ws.onopen = () => {
          if (fallbackActivated.current) {
            ws.close();
            return;
          }
          setConnected("live");
          if (fallbackTimer.current) {
            clearTimeout(fallbackTimer.current);
            fallbackTimer.current = null;
          }
        };
        ws.onclose = () => {
          if (!fallbackActivated.current) setConnected("offline");
          setTimeout(connect, 3000);
        };
        ws.onerror = () => ws.close();
        ws.onmessage = (msg) => {
          try {
            const parsed: LogEvent = JSON.parse(msg.data);
            onEvent?.(parsed);
          } catch {
            /* ignore */
          }
        };
      } catch {
        if (!fallbackActivated.current) {
          fallbackActivated.current = true;
          setConnected("polling");
        }
      }
    }

    // If WS doesn't open within 2s, give up and just rely on polling.
    fallbackTimer.current = window.setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState !== WebSocket.OPEN) {
        fallbackActivated.current = true;
        try { wsRef.current.close(); } catch { /* ignore */ }
        setConnected("polling");
      }
    }, 2000);

    connect();
    return () => {
      if (fallbackTimer.current) clearTimeout(fallbackTimer.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected, resetCursor: polling.resetCursor };
}
