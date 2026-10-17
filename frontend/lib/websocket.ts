"use client";

import { useEffect, useRef, useState } from "react";
import { api, type GalleryNode } from "@/lib/api";

// Default to 127.0.0.1 instead of localhost. Browsers and Python
// websockets both wait on IPv6→IPv4 fallback when the host is the
// string "localhost", which can add 2+ seconds of latency per WS
// handshake on Windows (Docker Desktop's loopback bridge is the
// usual culprit). Using the numeric IP bypasses the lookup and the
// fallback entirely.
const _host =
  typeof window !== "undefined" ? window.location.host : "localhost:8000";
const _numericHost = _host.replace(/^localhost/, "127.0.0.1");
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${_numericHost}`
    : "ws://127.0.0.1:8000");

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

// ---- Gallery streaming tree ----
//
// Opens a WebSocket to /api/gallery/stream and accumulates FolderNode
// messages into a partial tree as the server walks the filesystem.
// Components can render folders whose `rel_path` is already in `nodes`,
// and show a skeleton for any folder the walker hasn't reached yet.
//
// The hook tears down the WS as soon as `path` changes (or the
// component unmounts), so navigating away stops the server walk at its
// next folder boundary via the disconnect handler we wired up in
// gallery.py.

export type GalleryStreamNode = {
  type: "node" | "batch" | "done" | "error";
  // Single-node payload (kept for compatibility / debugging).
  data?: GalleryNode | null;
  // Batched payload — the server groups up to BATCH_SIZE nodes per
  // message because each ws.send() is hundreds of µs through Docker
  // Desktop's loopback bridge, and 300+ folder scans turn into
  // several seconds of cumulative overhead.
  nodes?: GalleryNode[];
  total?: number;
  detail?: string;
};

export function useGalleryStream(
  key: string | null,
  args: {
    path: string | null;
    depth?: number;
    maxNodes?: number;
    includeFiles?: boolean;
  }
) {
  const { path, depth = 6, maxNodes = 8000, includeFiles = false } = args;
  const [tree, setTree] = useState<GalleryNode | null>(null);
  const [progress, setProgress] = useState<{ nodes: number; done: boolean; error: string | null }>({
    nodes: 0,
    done: false,
    error: null,
  });

  useEffect(() => {
    if (key === null || path === null) return;
    setTree(null);
    setProgress({ nodes: 0, done: false, error: null });
    // Map rel_path -> node so we can attach each streamed node under its
    // parent by rel_path. The walker sends the parent node first, so by
    // the time children arrive the parent already has a slot in the map.
    const byPath = new Map<string, GalleryNode>();
    let cancelled = false;
    // Reset lastRoot on every effect run — when path changes the new
    // root may share a rel_path with a previous run (e.g. clicking
    // back into a folder), and a stale `lastRoot` would otherwise be
    // returned by `render()` and freeze the UI on the old subtree.
    let lastRoot: GalleryNode | null = null;

    // ----- HTTP fallback -----
    // The Gallery page used to lock up if the WS died for any reason
    // (proxy drop, IPv6 fallback hang, dev-server restart). We hit
    // the cached /api/gallery/tree endpoint once and feed its result
    // through the same attach() / render() pipeline. We only fall
    // back when WS has not delivered useful data yet — a single
    // root node alone doesn't count, since the user can't navigate
    // to anything below it.
    const tryHttpFallback = (reason: string) => {
      if (cancelled) return;
      if (byPath.size > 1) return;
      const params = new URLSearchParams({
        path,
        depth: String(depth),
        max_nodes: String(maxNodes),
        include_files: String(includeFiles),
      });
      fetch(`/api/gallery/tree?${params}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((root: GalleryNode) => {
          if (cancelled) return;
          attach(root);
          // Walk the full subtree so byPath has a slot for every
          // sub-folder the user might click next.
          const walk = (n: GalleryNode) => {
            for (const c of n.children || []) {
              attach(c);
              walk(c);
            }
          };
          walk(root);
          render(byPath.size);
          setProgress((p) => ({ ...p, done: true, error: `WS ${reason} — used HTTP fallback` }));
        })
        .catch((e) => {
          if (cancelled) return;
          setProgress((p) => ({ ...p, error: `${reason}; HTTP fallback: ${e?.message ?? e}`, done: true }));
        });
    };

    const url = `${WS_BASE}/api/gallery/stream`;
    const ws = new WebSocket(url);
    // 5s is enough for 488 nodes on the local box; if nothing
    // arrives, assume the upgrade is dead and go fetch.
    const fallbackTimer = window.setTimeout(() => {
      if (byPath.size === 0) tryHttpFallback("timeout 5s");
    }, 5000);
    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          path,
          depth,
          max_nodes: maxNodes,
          include_files: includeFiles,
        })
      );
    };
    // Nodes that arrived before their parent did. The walker sends the
    // parent node first, but with batched messages a child can land in
    // the same payload as its parent, or a batch can arrive a frame
    // before the parent on a slow link. We keep an id -> node map and
    // re-attach on every batch / single-node / done event.
    const pendingChildren = new Map<string, GalleryNode>();
    const attach = (n: GalleryNode) => {
      byPath.set(n.rel_path, n);
      pendingChildren.delete(n.rel_path);
      const idx = n.rel_path.lastIndexOf("/");
      let parentPath: string | null = null;
      if (idx > 0) {
        parentPath = n.rel_path.slice(0, idx);
      } else if (idx < 0 && path === "" && n.rel_path) {
        parentPath = ""; // direct child of gallery root
      }
      if (parentPath === null) return;
      const parent = byPath.get(parentPath);
      if (parent) {
        parent.children = parent.children || [];
        if (!parent.children.some((c) => c.rel_path === n.rel_path)) {
          parent.children.push(n);
        }
      } else {
        pendingChildren.set(n.rel_path, n);
      }
    };
    const drainPending = () => {
      // Re-attach everything in pending, leaving behind nodes whose
      // parent still hasn't arrived. Bounded by pass count + a stop
      // early-exit when no progress is made, so an orphan flood can't
      // pin the event loop.
      for (let pass = 0; pass < 25 && pendingChildren.size > 0; pass++) {
        const before = pendingChildren.size;
        for (const n of pendingChildren.values()) attach(n);
        if (pendingChildren.size === before) break; // no progress
      }
    };
    const render = (bump: number) => {
      // The walker streams the requested folder as the root node, with
      // rel_path == path (e.g. "instagram" when the user clicked that
      // folder). The empty string only appears as the root rel_path
      // when the user asked for the gallery root.
      const root = byPath.get(path) || byPath.get("") || lastRoot;
      if (!root) return;
      lastRoot = root;
      setTree({ ...root });
      setProgress((p) => ({ ...p, nodes: p.nodes + bump }));
    };
    ws.onmessage = (msg) => {
      try {
        const ev: GalleryStreamNode = JSON.parse(msg.data);
        if (ev.type === "node" && ev.data) {
          attach(ev.data);
          drainPending();
          render(1);
        } else if (ev.type === "batch" && ev.nodes) {
          for (const n of ev.nodes) attach(n);
          drainPending();
          render(ev.nodes.length);
        } else if (ev.type === "done") {
          drainPending();
          render(0);
          setProgress((p) => ({ ...p, done: true, nodes: ev.total ?? p.nodes }));
        } else if (ev.type === "error") {
          setProgress((p) => ({ ...p, error: ev.detail ?? "stream error", done: true }));
        }
      } catch {
        /* ignore */
      }
    };
    ws.onerror = () => {
      tryHttpFallback("error");
    };
    ws.onclose = () => {
      tryHttpFallback("closed");
    };
    return () => {
      cancelled = true;
      window.clearTimeout(fallbackTimer);
      try { ws.close(); } catch { /* ignore */ }
    };
  }, [key, path, depth, maxNodes, includeFiles]);

  return { tree, ...progress };
}
