"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type GalleryNode, type GalleryFileInfo, type GallerySearchItem, type GalleryStats, type GalleryKind } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Search, Folder, FolderOpen, File as FileIcon, ChevronRight, ChevronDown,
  ArrowUp, RefreshCw, Trash2, Edit3, X, Download, Image as ImageIcon, Film,
  FileText, Box, HardDrive, Loader2, FolderTree, LayoutGrid, List as ListIcon,
  ArrowDownAZ, ArrowDownZA, Clock, ArrowUpDown, ChevronUp,
} from "lucide-react";
import { formatBytes, cn } from "@/lib/utils";
import { sortNodes, type SortDir, type SortKey } from "@/lib/gallery-sort";
import { toast } from "sonner";

const API = (() => {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ||
    (typeof window !== "undefined" ? `${window.location.protocol}//${window.location.host}` : "http://localhost:8000");
  return base;
})();

const kindIcon = (k: GalleryKind | undefined) => {
  if (k === "image") return ImageIcon;
  if (k === "video") return Film;
  if (k === "text") return FileText;
  return FileIcon;
};
const kindColor = (k: GalleryKind | undefined) => {
  if (k === "image") return "from-primary/30 to-accent/20 text-primary";
  if (k === "video") return "from-accent/30 to-primary/20 text-accent";
  if (k === "text") return "from-warning/30 to-warning/10 text-warning";
  return "from-muted to-muted text-muted-foreground";
};

export default function GalleryPage() {
  const [currentPath, setCurrentPath] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  // Currently-open file in the right-side drawer. We also keep the
  // sibling list + index so arrow keys can step to the next/prev file
  // in the same folder or search result without leaving the drawer.
  const [selected, setSelected] = useState<{
    file: GalleryFileInfo;
    siblings: { rel_path: string }[];
    index: number;
  } | null>(null);

  // Arrow keys step through siblings while a file is open in the
  // drawer. Listener is on `window` (not the drawer) so it works
  // regardless of which element has focus; we skip the key when the
  // user is typing in a text field.
  useEffect(() => {
    if (!selected) return;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (!selected) return;
      let next: number | null = null;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") next = selected.index + 1;
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = selected.index - 1;
      else if (e.key === "Escape") { setSelected(null); return; }
      if (next === null) return;
      if (next < 0 || next >= selected.siblings.length) return;
      e.preventDefault();
      const nextFile = selected.siblings[next];
      api.get<GalleryFileInfo>("/api/gallery/file", { params: { path: nextFile.rel_path } })
        .then((r) => setSelected({ file: r.data, siblings: selected.siblings, index: next! }))
        .catch(() => { /* keep current file if fetch fails */ });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);
  const [statsOpen, setStatsOpen] = useState(false);
  // Display + sort preferences (persisted in localStorage so the choice
  // survives page reloads).
  type ViewMode = "grid" | "list";
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  useEffect(() => {
    try {
      const raw = localStorage.getItem("gallery:view");
      if (raw) {
        const p = JSON.parse(raw);
        if (p.viewMode === "grid" || p.viewMode === "list") setViewMode(p.viewMode);
        if (p.sortKey === "name" || p.sortKey === "ctime") setSortKey(p.sortKey);
        if (p.sortDir === "asc" || p.sortDir === "desc") setSortDir(p.sortDir);
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem("gallery:view", JSON.stringify({ viewMode, sortKey, sortDir })); } catch { /* ignore */ }
  }, [viewMode, sortKey, sortDir]);

  const qc = useQueryClient();

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // ---- Tree (lazy-load subdirs on click) ----
  const { data: tree, isLoading: treeLoading } = useQuery({
    queryKey: ["gallery-tree", currentPath],
    queryFn: async () =>
      (await api.get<GalleryNode>("/api/gallery/browse", { params: { path: currentPath } })).data,
    enabled: debouncedSearch === "",
  });

  // ---- Search ----
  const { data: searchResult, isFetching: searchLoading } = useQuery({
    queryKey: ["gallery-search", debouncedSearch],
    queryFn: async () =>
      (await api.get<{ total: number; items: GallerySearchItem[] }>("/api/gallery/search", {
        params: { q: debouncedSearch, limit: 500 },
      })).data,
    enabled: debouncedSearch.length > 0,
  });

  // ---- Stats ----
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ["gallery-stats"],
    queryFn: async () => (await api.get<GalleryStats>("/api/gallery/stats")).data,
    enabled: statsOpen,
  });

  function goUp() {
    if (!currentPath) return;
    const parts = currentPath.split("/").filter(Boolean);
    parts.pop();
    setCurrentPath(parts.join("/"));
  }
  function goHome() {
    setCurrentPath("");
    setSearch("");
  }
  function navigateTo(rel: string) {
    setCurrentPath(rel);
    setSearch("");
  }
  function refresh() {
    qc.invalidateQueries({ queryKey: ["gallery-tree", currentPath] });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            <span className="gradient-text">Gallery</span>
          </h2>
          <p className="text-muted-foreground mt-1 flex items-center gap-2 font-mono text-xs">
            <HardDrive className="h-3.5 w-3.5" />
            E:\gallery-dl
            {currentPath && <span className="text-primary">/ {currentPath}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={statsOpen ? "default" : "outline"}
            size="sm"
            onClick={() => setStatsOpen((x) => !x)}
            className="gap-2"
          >
            <Box className="h-4 w-4" /> Stats
          </Button>
          <Button variant="outline" size="sm" onClick={refresh} className="gap-2">
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        </div>
      </div>

      {statsOpen && (
        <StatsPanel stats={stats} loading={statsLoading} onRefresh={() => refetchStats()} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* ---- Tree sidebar ---- */}
        <Card variant="glass" className="hidden lg:block h-fit sticky top-20 max-h-[calc(100vh-6rem)] overflow-hidden flex flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FolderTree className="h-4 w-4 text-primary" /> Tree
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2 overflow-y-auto flex-1">
            {treeLoading && !tree ? (
              <div className="p-4 text-xs text-muted-foreground flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading...
              </div>
            ) : tree ? (
              <TreeView
                node={tree}
                level={0}
                currentPath={currentPath}
                onNavigate={navigateTo}
              />
            ) : null}
          </CardContent>
        </Card>

        {/* ---- Main pane ---- */}
        <div className="space-y-4 min-w-0">
          <Card variant="glass" className="p-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={goHome}
                className="gap-1.5"
                title="Back to root"
              >
                <Folder className="h-3.5 w-3.5" /> Root
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={goUp}
                disabled={!currentPath}
                title="Up one level"
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
              <Breadcrumb currentPath={currentPath} onNavigate={navigateTo} />

              <div className="ml-auto flex items-center gap-2">
                {/* View mode toggle */}
                <div className="flex items-center rounded-md border border-white/10 overflow-hidden">
                  <button
                    onClick={() => setViewMode("grid")}
                    className={cn(
                      "px-2 py-1 flex items-center gap-1 text-xs transition-colors",
                      viewMode === "grid" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-white/5"
                    )}
                    title="Grid view"
                  >
                    <LayoutGrid className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => setViewMode("list")}
                    className={cn(
                      "px-2 py-1 flex items-center gap-1 text-xs transition-colors border-l border-white/10",
                      viewMode === "list" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-white/5"
                    )}
                    title="List view"
                  >
                    <ListIcon className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Sort selector */}
                <div className="flex items-center gap-1 rounded-md border border-white/10 bg-background/40 px-1.5 py-1">
                  <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                  <select
                    value={sortKey}
                    onChange={(e) => setSortKey(e.target.value as SortKey)}
                    className="bg-transparent text-xs focus:outline-none"
                    title="Sort by"
                  >
                    <option value="name">Theo kí tự (Name)</option>
                    <option value="ctime">Theo thời gian (folder: file mới nhất)</option>
                  </select>
                  <button
                    onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                    className="ml-1 p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-foreground"
                    title={`Sort ${sortDir === "asc" ? "ascending" : "descending"} — click to toggle`}
                  >
                    {sortDir === "asc" ? <ArrowDownAZ className="h-3.5 w-3.5" /> : <ArrowDownZA className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>
            </div>
            <div className="relative mt-2">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search filenames across whole gallery..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-background/50"
              />
              {searchLoading && (
                <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
              )}
            </div>
          </Card>

          {debouncedSearch ? (
            <SearchResults
              result={searchResult}
              loading={searchLoading}
              onSelect={async (item, siblings, index) => {
                const r = await api.get<GalleryFileInfo>("/api/gallery/file", { params: { path: item.rel_path } });
                setSelected({ file: r.data, siblings, index });
              }}
              viewMode={viewMode}
              sortKey={sortKey}
              sortDir={sortDir}
            />
          ) : tree ? (
            <FolderView
              node={tree}
              onOpenFile={async (file, siblings, index) => {
                const r = await api.get<GalleryFileInfo>("/api/gallery/file", { params: { path: file.rel_path } });
                setSelected({ file: r.data, siblings, index });
              }}
              onEnterFolder={(child) => navigateTo(child.rel_path)}
              currentPath={currentPath}
              qc={qc}
              onChanged={refresh}
              viewMode={viewMode}
              sortKey={sortKey}
              sortDir={sortDir}
            />
          ) : (
            <Card variant="glass" className="p-12 text-center text-muted-foreground">
              Loading...
            </Card>
          )}
        </div>
      </div>

      {selected && (
        <FileDrawer file={selected.file} onClose={() => setSelected(null)} onChanged={refresh} qc={qc} />
      )}
    </div>
  );
}

// =====================================================================
// Subcomponents
// =====================================================================

function Breadcrumb({ currentPath, onNavigate }: { currentPath: string; onNavigate: (p: string) => void }) {
  const parts = currentPath.split("/").filter(Boolean);
  return (
    <div className="flex items-center gap-1 text-sm font-mono overflow-x-auto">
      {parts.map((p, i) => {
        const path = parts.slice(0, i + 1).join("/");
        return (
          <div key={path} className="flex items-center gap-1">
            <button
              onClick={() => onNavigate(path)}
              className="px-2 py-1 rounded hover:bg-white/10 text-foreground/80 hover:text-foreground transition-colors"
            >
              {p}
            </button>
            {i < parts.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </div>
        );
      })}
    </div>
  );
}

function TreeView({
  node,
  level,
  currentPath,
  onNavigate,
}: {
  node: GalleryNode;
  level: number;
  currentPath: string;
  onNavigate: (p: string) => void;
}) {
  const isExpanded = currentPath === node.rel_path || currentPath.startsWith(node.rel_path + "/");
  const isCurrent = currentPath === node.rel_path;
  const [open, setOpen] = useState(isExpanded);

  useEffect(() => {
    if (isExpanded) setOpen(true);
  }, [isExpanded]);

  const subfolders = (node.children || []).filter((c) => c.is_dir);

  if (level === 0) {
    // Root - render children inline, always open
    return (
      <div className="space-y-0.5">
        {subfolders.map((c) => (
          <TreeView
            key={c.rel_path}
            node={c}
            level={level + 1}
            currentPath={currentPath}
            onNavigate={onNavigate}
          />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => {
          setOpen((x) => !x);
          onNavigate(node.rel_path);
        }}
        className={cn(
          "w-full flex items-center gap-1.5 px-2 py-1 rounded text-xs hover:bg-white/5 transition-colors text-left",
          isCurrent && "bg-primary/15 text-primary"
        )}
        style={{ paddingLeft: `${level * 12 + 4}px` }}
      >
        {subfolders.length > 0 ? (
          open ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />
        ) : (
          <span className="w-3 shrink-0" />
        )}
        {open ? (
          <FolderOpen className="h-3.5 w-3.5 shrink-0 text-primary" />
        ) : (
          <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate flex-1">{node.name}</span>
        {node.folder_count > 0 && (
          <span className="text-[10px] text-muted-foreground font-mono">
            {node.folder_count}
          </span>
        )}
      </button>
      {open && subfolders.length > 0 && (
        <div>
          {subfolders.map((c) => (
            <TreeView
              key={c.rel_path}
              node={c}
              level={level + 1}
              currentPath={currentPath}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FolderView({
  node,
  onOpenFile,
  onEnterFolder,
  currentPath,
  qc,
  onChanged,
  viewMode,
  sortKey,
  sortDir,
}: {
  node: GalleryNode;
  onOpenFile: (f: GalleryNode, siblings: GalleryNode[], index: number) => void;
  onEnterFolder: (f: GalleryNode) => void;
  currentPath: string;
  qc: ReturnType<typeof useQueryClient>;
  onChanged: () => void;
  viewMode: "grid" | "list";
  sortKey: SortKey;
  sortDir: SortDir;
}) {
  const children = node.children || [];
  const folders = children.filter((c) => c.is_dir);
  const files = children.filter((c) => !c.is_dir);

  // Folders and files sort independently (folders always render first).
  // "Time" means mtime for folders so a folder you just downloaded into
  // floats to the top — see lib/gallery-sort.ts.
  const sortedFiles = sortNodes<GalleryNode>(files, sortKey, sortDir);
  const sortedFolders = sortNodes<GalleryNode>(folders, sortKey, sortDir);

  return (
    <>
      {sortedFolders.length > 0 && (
        <Card variant="glass">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FolderOpen className="h-4 w-4 text-primary" /> {sortedFolders.length} folders
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            {viewMode === "grid" ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                {sortedFolders.map((f, i) => (
                  <FolderCard
                    key={f.rel_path}
                    node={f}
                    onClick={() => onEnterFolder(f)}
                    qc={qc}
                    currentPath={currentPath}
                    onChanged={onChanged}
                    delay={i}
                  />
                ))}
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {sortedFolders.map((f, i) => (
                  <FolderRow
                    key={f.rel_path}
                    node={f}
                    onClick={() => onEnterFolder(f)}
                    delay={i}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {sortedFiles.length > 0 && (
        <Card variant="glass">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileIcon className="h-4 w-4 text-accent" /> {sortedFiles.length} files · {formatBytes(node.size_bytes)}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {viewMode === "grid" ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 p-3">
                {sortedFiles.map((f, i) => (
                  <FileCard key={f.rel_path} node={f} onClick={() => onOpenFile(f, sortedFiles, i)} delay={i} />
                ))}
              </div>
            ) : (
              <div className="divide-y divide-white/5 max-h-[60vh] overflow-y-auto">
                {sortedFiles.map((f, i) => (
                  <FileRow
                    key={f.rel_path}
                    node={f}
                    onClick={() => onOpenFile(f, sortedFiles, i)}
                    delay={i}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {sortedFolders.length === 0 && sortedFiles.length === 0 && (
        <Card variant="glass" className="p-12 text-center text-muted-foreground">
          Empty folder
        </Card>
      )}
    </>
  );
}

function FolderCard({
  node,
  onClick,
  qc,
  currentPath,
  onChanged,
  delay,
}: {
  node: GalleryNode;
  onClick: () => void;
  qc: ReturnType<typeof useQueryClient>;
  currentPath: string;
  onChanged: () => void;
  delay: number;
}) {
  const [confirm, setConfirm] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(node.name);

  const renameMut = useMutation({
    mutationFn: async (name: string) =>
      (await api.post("/api/gallery/rename", { new_name: name }, { params: { path: node.rel_path } })).data,
    onSuccess: () => {
      toast.success("Renamed");
      setRenaming(false);
      qc.invalidateQueries({ queryKey: ["gallery-tree"] });
      onChanged();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Rename failed"),
  });

  const deleteMut = useMutation({
    mutationFn: async () =>
      (await api.delete("/api/gallery", { params: { path: node.rel_path, confirm: true } })).data,
    onSuccess: () => {
      toast.success(`Deleted folder ${node.name}`);
      qc.invalidateQueries({ queryKey: ["gallery-tree"] });
      onChanged();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Delete failed"),
  });

  return (
    <div
      className="group relative rounded-lg border border-white/5 bg-card/40 hover:border-primary/40 transition-all p-3 fade-in-up"
      style={{ animationDelay: `${delay * 30}ms` }}
    >
      {renaming ? (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="h-7 text-xs"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") renameMut.mutate(newName);
              if (e.key === "Escape") setRenaming(false);
            }}
          />
          <Button size="sm" variant="ghost" onClick={() => renameMut.mutate(newName)}>OK</Button>
        </div>
      ) : (
        <button onClick={onClick} className="w-full text-left">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-md bg-primary/15 flex items-center justify-center group-hover:bg-primary/25 transition-colors">
              <FolderOpen className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate" title={node.name}>{node.name}</div>
              <div className="text-[10px] text-muted-foreground font-mono">
                {node.folder_count > 0 && `${node.folder_count}f · `}
                {node.file_count > 0 && `${node.file_count} files`}
                {node.file_count === 0 && node.folder_count === 0 && "empty"}
              </div>
            </div>
          </div>
        </button>
      )}

      {!renaming && (
        <div className="absolute top-2 right-2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setRenaming(true);
            }}
            className="p-1 rounded hover:bg-white/10"
            title="Rename"
          >
            <Edit3 className="h-3 w-3" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setConfirm(true);
            }}
            className="p-1 rounded hover:bg-destructive/20"
            title="Delete"
          >
            <Trash2 className="h-3 w-3 text-destructive" />
          </button>
        </div>
      )}

      {confirm && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-black/80 backdrop-blur-sm p-2"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-center space-y-2">
            <div className="text-xs text-muted-foreground">Delete <span className="font-mono text-destructive">{node.name}</span>?</div>
            <div className="flex gap-1 justify-center">
              <Button size="sm" variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
                {deleteMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Yes"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>No</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FileCard({ node, onClick, delay }: { node: GalleryNode; onClick: () => void; delay: number }) {
  const [thumbError, setThumbError] = useState(false);
  const isImage = isImageExt(node.ext ?? "");
  const isVideo = isVideoExt(node.ext ?? "");
  const showThumb = isImage && !thumbError;

  return (
    <button
      onClick={onClick}
      className="group relative overflow-hidden rounded-lg border border-white/5 bg-card/40 hover:border-primary/40 transition-all hover:-translate-y-0.5 fade-in-up text-left"
      style={{ animationDelay: `${Math.min(delay, 12) * 20}ms` }}
    >
      <div className="aspect-square bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center relative overflow-hidden">
        {showThumb ? (
          <img
            src={`${API}/api/gallery/raw?path=${encodeURIComponent(node.rel_path)}`}
            alt={node.name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            loading="lazy"
            onError={() => setThumbError(true)}
          />
        ) : isVideo ? (
          <Film className="h-8 w-8 text-accent/60 group-hover:text-accent transition-colors" />
        ) : (
          <FileIcon className="h-8 w-8 text-muted-foreground/60 group-hover:text-foreground transition-colors" />
        )}
        <div className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/60 backdrop-blur">
          {formatBytes(node.size_bytes)}
        </div>
      </div>
      <div className="p-2">
        <div className="text-xs font-medium truncate" title={node.name}>{node.name}</div>
      </div>
    </button>
  );
}

// Compact row used in the "list" view mode — shows more metadata per file
// at the cost of horizontal density. Mirrors the layout of SearchResults.
function FileRow({ node, onClick, delay }: { node: GalleryNode; onClick: () => void; delay: number }) {
  const ext = node.ext ?? "";
  const Icon = isVideoExt(ext) ? Film : isImageExt(ext) ? ImageIcon : FileIcon;
  const ts = node.ctime ?? node.mtime;
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 hover:bg-white/5 transition-colors text-left fade-in-up"
      style={{ animationDelay: `${Math.min(delay, 12) * 15}ms` }}
    >
      <div className={cn(
        "h-8 w-8 rounded-md flex items-center justify-center bg-gradient-to-br shrink-0",
        isImageExt(ext) ? "from-primary/30 to-accent/20 text-primary"
        : isVideoExt(ext) ? "from-accent/30 to-primary/20 text-accent"
        : "from-muted to-muted text-muted-foreground"
      )}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{node.name}</div>
        <div className="text-[11px] text-muted-foreground font-mono truncate">
          {node.ext || "(no ext)"} · {node.rel_path}
        </div>
      </div>
      <div className="text-xs text-muted-foreground text-right shrink-0 hidden sm:block">
        <div className="font-mono">{formatBytes(node.size_bytes)}</div>
        <div>{new Date(ts * 1000).toLocaleDateString()}</div>
      </div>
      <div className="sm:hidden text-[10px] text-muted-foreground font-mono shrink-0">
        {formatBytes(node.size_bytes)}
      </div>
    </button>
  );
}

// List-mode row for a folder entry. Mirrors FileRow so the two sections
// (folders + files) line up in list view.
function FolderRow({ node, onClick, delay }: { node: GalleryNode; onClick: () => void; delay: number }) {
  const ts = node.ctime ?? node.mtime;
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 hover:bg-white/5 transition-colors text-left fade-in-up"
      style={{ animationDelay: `${Math.min(delay, 12) * 15}ms` }}
    >
      <div className="h-8 w-8 rounded-md bg-primary/15 flex items-center justify-center shrink-0">
        <FolderOpen className="h-4 w-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{node.name}</div>
        <div className="text-[11px] text-muted-foreground font-mono truncate">
          {node.folder_count > 0 && `${node.folder_count} folders · `}
          {node.file_count > 0 && `${node.file_count} files`}
          {node.file_count === 0 && node.folder_count === 0 && "empty"}
        </div>
      </div>
      <div className="text-xs text-muted-foreground text-right shrink-0 hidden sm:block">
        <div className="font-mono">{formatBytes(node.size_bytes)}</div>
        <div>{new Date(ts * 1000).toLocaleDateString()}</div>
      </div>
    </button>
  );
}

function isImageExt(ext: string): boolean {
  return [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"].includes(ext);
}
function isVideoExt(ext: string): boolean {
  return [".mp4", ".webm", ".mov"].includes(ext);
}

function SearchResults({
  result,
  loading,
  onSelect,
  sortKey,
  sortDir,
  viewMode,
}: {
  result: { total: number; items: GallerySearchItem[] } | undefined;
  loading: boolean;
  onSelect: (item: GallerySearchItem, siblings: GallerySearchItem[], index: number) => void | Promise<void>;
  sortKey: SortKey;
  sortDir: SortDir;
  viewMode: "grid" | "list";
}) {
  const sorted = sortNodes<GallerySearchItem>(result?.items ?? [], sortKey, sortDir);
  if (loading) {
    return (
      <Card variant="glass" className="p-12 text-center text-muted-foreground flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" /> Searching...
      </Card>
    );
  }
  if (!result || result.items.length === 0) {
    return (
      <Card variant="glass" className="p-12 text-center text-muted-foreground">
        No files match your search
      </Card>
    );
  }
  return (
    <>
      <div className="text-xs text-muted-foreground px-1">
        Found <span className="font-mono text-primary">{result.total.toLocaleString()}</span> files
        {result.items.length < result.total && ` (showing first ${result.items.length})`}
      </div>
      <Card variant="glass">
        <CardContent className="p-0">
          <div className="grid grid-cols-[2.5rem_1fr_auto] sm:grid-cols-[2.5rem_1fr_8rem_6rem] gap-3 items-center px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5 font-mono">
            <span></span>
            <span>name · path</span>
            <span className="hidden sm:block text-right">size</span>
            <span className="text-right">{sortKey === "ctime" ? "created" : "modified"}</span>
          </div>
          <div className="divide-y divide-white/5 max-h-[60vh] overflow-y-auto">
            {sorted.map((it, i) => {
              const Icon = kindIcon(it.kind);
              return (
                <button
                  key={it.rel_path + i}
                  onClick={() => onSelect(it, sorted, i)}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/5 transition-colors text-left fade-in-up"
                  style={{ animationDelay: `${Math.min(i, 12) * 15}ms` }}
                >
                  <div className={cn("h-8 w-8 rounded-md flex items-center justify-center bg-gradient-to-br", kindColor(it.kind))}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{it.name}</div>
                    <div className="text-xs text-muted-foreground font-mono truncate">{it.rel_path}</div>
                  </div>
                  <div className="text-xs text-muted-foreground text-right shrink-0">
                    <div className="font-mono">{formatBytes(it.size_bytes)}</div>
                    <div>{new Date(it.mtime * 1000).toLocaleDateString()}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </>
  );
}

function FileDrawer({
  file,
  onClose,
  onChanged,
  qc,
}: {
  file: GalleryFileInfo;
  onClose: () => void;
  onChanged: () => void;
  qc: ReturnType<typeof useQueryClient>;
}) {
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(file.name);
  const [confirm, setConfirm] = useState(false);
  const isImage = ["image"].includes(file.kind);
  const isVideo = ["video"].includes(file.kind);

  const renameMut = useMutation({
    mutationFn: async (name: string) =>
      (await api.post("/api/gallery/rename", { new_name: name }, { params: { path: file.rel_path } })).data,
    onSuccess: () => {
      toast.success("Renamed");
      setRenaming(false);
      onChanged();
      onClose();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Rename failed"),
  });

  const deleteMut = useMutation({
    mutationFn: async () =>
      (await api.delete("/api/gallery", { params: { path: file.rel_path, confirm: true } })).data,
    onSuccess: () => {
      toast.success(`Deleted ${file.name}`);
      qc.invalidateQueries({ queryKey: ["gallery-stats"] });
      onChanged();
      onClose();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Delete failed"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative w-full max-w-4xl max-h-[90vh] rounded-xl border border-white/10 bg-card/95 backdrop-blur-xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-white/5">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {renaming ? (
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="h-8"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") renameMut.mutate(newName);
                  if (e.key === "Escape") setRenaming(false);
                }}
              />
            ) : (
              <>
                <div className={cn("h-8 w-8 rounded-md flex items-center justify-center bg-gradient-to-br", kindColor(file.kind))}>
                  {(() => {
                    const Icon = kindIcon(file.kind);
                    return <Icon className="h-4 w-4" />;
                  })()}
                </div>
                <div className="min-w-0">
                  <div className="font-semibold truncate">{file.name}</div>
                  <div className="text-xs text-muted-foreground font-mono truncate">{file.rel_path}</div>
                </div>
              </>
            )}
          </div>
          <button onClick={onClose} className="p-2 rounded hover:bg-white/10 shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto bg-black/50 flex items-center justify-center min-h-[300px]">
          {isImage ? (
            <img
              src={`${API}/api/gallery/raw?path=${encodeURIComponent(file.rel_path)}`}
              alt={file.name}
              className="max-w-full max-h-[70vh] object-contain"
            />
          ) : isVideo ? (
            <video
              src={`${API}/api/gallery/raw?path=${encodeURIComponent(file.rel_path)}`}
              controls
              className="max-w-full max-h-[70vh]"
            />
          ) : (
            <div className="text-center p-12">
              <div className={cn("inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br mb-4", kindColor(file.kind))}>
                {(() => {
                  const Icon = kindIcon(file.kind);
                  return <Icon className="h-10 w-10" />;
                })()}
              </div>
              <div className="text-sm text-muted-foreground">No preview available</div>
              <div className="text-xs text-muted-foreground font-mono mt-1">{file.mime}</div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-white/5 flex items-center justify-between gap-2 flex-wrap">
          <div className="text-xs text-muted-foreground font-mono space-x-4">
            <span>{formatBytes(file.size_bytes)}</span>
            <span>{file.mime}</span>
            <span>{new Date(file.mtime * 1000).toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2">
            {renaming ? (
              <>
                <Button size="sm" onClick={() => renameMut.mutate(newName)} disabled={renameMut.isPending}>
                  {renameMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => setRenaming(true)}>
                  <Edit3 className="h-3.5 w-3.5" /> Rename
                </Button>
                <a
                  href={`${API}/api/gallery/download?path=${encodeURIComponent(file.rel_path)}`}
                  download
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                >
                  <Download className="h-3.5 w-3.5" /> Download
                </a>
                <Button size="sm" variant="destructive" onClick={() => setConfirm(true)}>
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </Button>
              </>
            )}
          </div>
        </div>

        {confirm && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80 backdrop-blur-sm rounded-xl">
            <div className="text-center space-y-4 p-6">
              <Trash2 className="h-12 w-12 mx-auto text-destructive" />
              <div className="font-semibold">Delete this file?</div>
              <div className="text-sm text-muted-foreground max-w-md">
                <span className="font-mono text-foreground">{file.name}</span>
                <br />
                will be permanently removed from disk.
              </div>
              <div className="flex gap-2 justify-center">
                <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
                  {deleteMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Delete permanently"}
                </Button>
                <Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatsPanel({
  stats,
  loading,
  onRefresh,
}: {
  stats: GalleryStats | undefined;
  loading: boolean;
  onRefresh: () => void;
}) {
  if (loading && !stats) {
    return (
      <Card variant="glass" className="p-6 text-center text-muted-foreground flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" /> Scanning gallery (may take a while)...
      </Card>
    );
  }
  if (!stats) return null;

  return (
    <Card variant="glass" className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Gallery statistics</div>
        <Button variant="ghost" size="sm" onClick={onRefresh}><RefreshCw className="h-3 w-3" /></Button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatBox label="Files" value={stats.total_files.toLocaleString()} gradient="from-primary/20 to-primary/5" />
        <StatBox label="Folders" value={stats.total_folders.toLocaleString()} gradient="from-accent/20 to-accent/5" />
        <StatBox label="Total size" value={formatBytes(stats.total_size_bytes)} gradient="from-warning/20 to-warning/5" />
        <StatBox
          label="Top folder"
          value={Object.entries(stats.by_top_folder)[0]?.[0] ?? "—"}
          sub={Object.entries(stats.by_top_folder)[0]?.[1]?.toLocaleString() + " files"}
          gradient="from-success/20 to-success/5"
        />
      </div>

      {Object.keys(stats.by_extension).length > 0 && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            By extension
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(stats.by_extension).map(([ext, n]) => (
              <div key={ext} className="px-2 py-1 rounded-md bg-white/5 text-xs font-mono flex items-center gap-1.5">
                <span className="text-primary">{ext || "(none)"}</span>
                <span className="text-muted-foreground">{n.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats.largest_files.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Largest files
          </div>
          <div className="space-y-1">
            {stats.largest_files.slice(0, 5).map((f) => (
              <div key={f.rel_path} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-foreground truncate flex-1">{f.name}</span>
                <span className="text-muted-foreground shrink-0">{formatBytes(f.size_bytes)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function StatBox({ label, value, sub, gradient }: { label: string; value: string; sub?: string; gradient: string }) {
  return (
    <div className={cn("relative rounded-lg border border-white/5 bg-gradient-to-br p-3 overflow-hidden", gradient)}>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">{label}</div>
      <div className="text-lg font-bold mt-1 truncate">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

// useMutation already imported above
