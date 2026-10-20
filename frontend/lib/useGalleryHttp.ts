"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { GalleryNode } from "@/lib/api";

/**
 * useGalleryHttp — pure-HTTP gallery state.
 *
 * The root fetch (`/api/gallery/tree?path=`) is folder-only by design
 * (include_files=false) so the sidebar stays light. Folder nodes from that
 * response carry `file_count` but NO file children, so they cannot render
 * media in the main pane.
 *
 * `fetchNode(relPath)` resolves a sub-folder with include_files=true and
 * stores it in `nodeByPath`. Each path is fetched at most once with files
 * (tracked in `filesFetchedRef`), so empty folders don't refetch forever.
 */
export function useGalleryHttp(opts: { path: string; depth?: number; includeFiles?: boolean; nonce?: number }) {
  const { depth = 1, includeFiles = false, nonce = 0 } = opts;
  const [root, setRoot] = useState<GalleryNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lazyByPath, setLazyByPath] = useState<Record<string, GalleryNode>>({});
  const [lazyLoadingPath, setLazyLoadingPath] = useState<string | null>(null);
  // nodeByPath: root seed + every node fetched with file children. Keys are
  // rel_path ("" = root).
  const [nodeByPath, setNodeByPath] = useState<Record<string, GalleryNode>>({});
  const filesFetchedRef = useRef<Set<string>>(new Set());
  // Paths whose node was fetched with include_files=true (authoritative
  // "ready to render media" flag used by the page).
  const [filesFetchedReady, setFilesFetchedReady] = useState<string[]>([]);

  // Root fetch — one shot; aborts stale requests on unmount / param change.
  useEffect(() => {
    const ctrl = new AbortController();
    setRoot(null);
    setNodeByPath({});
    setLazyByPath({});
    filesFetchedRef.current = new Set();
    setFilesFetchedReady([]);
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      path: "",
      depth: String(depth),
      max_nodes: "8000",
      include_files: String(includeFiles),
    });
    fetch(`/api/gallery/tree?${params}`, { signal: ctrl.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((rootNode: GalleryNode) => {
        setRoot(rootNode);
        const seed: Record<string, GalleryNode> = { "": rootNode };
        const walk = (n: GalleryNode) => {
          for (const c of n.children || []) {
            seed[c.rel_path] = c;
            walk(c);
          }
        };
        walk(rootNode);
        setNodeByPath(seed);
        setLoading(false);
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError(e?.message ?? String(e));
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [depth, includeFiles, nonce]);

  // Lazy load — sidebar tree expansion (folder-only children).
  const loadChildren = useCallback(
    (relPath: string) => {
      if (lazyByPath[relPath] || lazyLoadingPath === relPath) return;
      setLazyLoadingPath(relPath);
      const params = new URLSearchParams({
        path: relPath,
        depth: "1",
        max_nodes: "1000",
        include_files: "true",
      });
      fetch(`/api/gallery/tree?${params}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((sub: GalleryNode) => {
          filesFetchedRef.current.add(relPath);
          setLazyByPath((prev) => ({ ...prev, [relPath]: sub }));
          setNodeByPath((prev) => ({ ...prev, [relPath]: sub }));
          setFilesFetchedReady((prev) => (prev.includes(relPath) ? prev : [...prev, relPath]));
        })
        .catch((e) => {
          setError(e?.message ?? String(e));
        })
        .finally(() => setLazyLoadingPath(null));
    },
    [lazyByPath, lazyLoadingPath],
  );

  // fetchNode — make sure nodeByPath[relPath] has file children. Root ("")
  // stays folder-only and is never rendered as media.
  const fetchNode = useCallback(
    (relPath: string) => {
      if (relPath === "") return;
      if (filesFetchedRef.current.has(relPath)) return;
      filesFetchedRef.current.add(relPath);
      const params = new URLSearchParams({
        path: relPath,
        depth: "1",
        max_nodes: "1000",
        include_files: "true",
      });
      fetch(`/api/gallery/tree?${params}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((n: GalleryNode) => {
          setNodeByPath((prev) => ({ ...prev, [relPath]: n }));
          setFilesFetchedReady((prev) => (prev.includes(relPath) ? prev : [...prev, relPath]));
        })
        .catch((e) => {
          filesFetchedRef.current.delete(relPath);
          setError(e?.message ?? String(e));
        });
    },
    [],
  );

  return {
    tree: root,
    nodeByPath,
    loading,
    error,
    lazyByPath,
    lazyLoadingPath,
    loadChildren,
    fetchNode,
    readyPaths: filesFetchedReady,
  };
}
