"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Search, RefreshCw, ArrowUpDown, LayoutGrid, List as ListIcon, ExternalLink } from "lucide-react";
import { formatBytes, formatNumber, cn } from "@/lib/utils";

/**
 * Account rendered from a gallery subfolder. We don't query the `accounts`
 * DB table here on purpose — the user wanted the Accounts page to surface
 * the *actual* folders on disk under instagram/ and twitter/, one card per
 * folder, even for accounts that were never scanned into the DB.
 */
type AccountCard = {
  /** folder name (the username) */
  username: string;
  /** which platform folder it came from */
  platform: "instagram" | "twitter";
  /** full rel_path into the gallery, used to open it in the Gallery tab */
  rel_path: string;
  /** total bytes used by this account's folder (recursive) */
  size_bytes: number;
  /** number of files inside (recursive) */
  file_count: number;
  /** number of sub-folders (e.g. /posts, /stories, /highlights) */
  folder_count: number;
  /** most recent mtime across the account's files (used for "last seen") */
  mtime: number;
  /** ctime of the account folder itself (Windows creation time) */
  ctime: number;
  /** rough image / video breakdown for the badge */
  image_count: number;
  video_count: number;
};

const PLATFORMS = [
  { key: "instagram", label: "Instagram", accent: "from-pink-500/30 to-amber-400/20 text-pink-200" },
  { key: "twitter", label: "Twitter / X", accent: "from-sky-500/30 to-blue-500/20 text-sky-200" },
] as const;

const IMAGE_EXT = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]);
const VIDEO_EXT = new Set([".mp4", ".webm", ".mov"]);

export default function AccountsPage() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [sortKey, setSortKey] = useState<"username" | "size_bytes" | "mtime" | "file_count" | "ctime">("username");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim().toLowerCase()), 250);
    return () => clearTimeout(t);
  }, [search]);

  // Persist display prefs
  useEffect(() => {
    try {
      const raw = localStorage.getItem("accounts:view");
      if (raw) {
        const p = JSON.parse(raw);
        if (p.viewMode === "grid" || p.viewMode === "list") setViewMode(p.viewMode);
        if (["username", "size_bytes", "mtime", "file_count", "ctime"].includes(p.sortKey)) setSortKey(p.sortKey);
        if (p.sortDir === "asc" || p.sortDir === "desc") setSortDir(p.sortDir);
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem("accounts:view", JSON.stringify({ viewMode, sortKey, sortDir })); } catch { /* ignore */ }
  }, [viewMode, sortKey, sortDir]);

  // Single recursive scan of the gallery root — returns one entry per
  // account folder (instagram/<user>/* or twitter/<user>/*) with full
  // stats. Much faster than per-folder /browse calls on large trees.
  const scan = useQuery<{ total: number; platforms: string[]; accounts: AccountCard[] }>({
    queryKey: ["accounts-scan"],
    queryFn: async () => (await api.get("/api/accounts/scan-from-disk")).data,
    staleTime: 30_000,
  });

  const isLoading = scan.isLoading;
  const isFetching = scan.isFetching;

  // Already sorted by (platform, username) on the server, but we still
  // honour the user's sortKey/sortDir for client-side tweaks.
  const accounts = scan.data?.accounts ?? [];

  const filtered = useMemo(() => {
    let list = accounts;
    if (debounced) {
      list = list.filter((a) => a.username.toLowerCase().includes(debounced));
    }
    list = list.slice().sort((a, b) => {
      let cmp = 0;
      if (sortKey === "username") cmp = a.username.localeCompare(b.username, undefined, { numeric: true });
      else if (sortKey === "size_bytes") cmp = a.size_bytes - b.size_bytes;
      else if (sortKey === "mtime") cmp = a.mtime - b.mtime;
      else if (sortKey === "ctime") cmp = (a.ctime ?? 0) - (b.ctime ?? 0);
      else if (sortKey === "file_count") cmp = a.file_count - b.file_count;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [accounts, debounced, sortKey, sortDir]);

  const stats = useMemo(() => {
    const ig = accounts.filter((a) => a.platform === "instagram");
    const tw = accounts.filter((a) => a.platform === "twitter");
    const totalSize = accounts.reduce((s, a) => s + a.size_bytes, 0);
    const totalFiles = accounts.reduce((s, a) => s + a.file_count, 0);
    return {
      total: accounts.length,
      ig: ig.length,
      tw: tw.length,
      totalSize,
      totalFiles,
    };
  }, [accounts]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            <span className="gradient-text">Accounts</span>
          </h2>
          <p className="text-muted-foreground mt-1">
            {formatNumber(stats.total)} folders on disk · {formatBytes(stats.totalSize)} · {formatNumber(stats.totalFiles)} files
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => { scan.refetch(); }} variant="outline" size="sm" className="gap-2">
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      {/* Toolbar */}
      <Card variant="glass" className="p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by username..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-background/50"
            />
          </div>

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

          <div className="flex items-center gap-1 rounded-md border border-white/10 bg-background/40 px-1.5 py-1">
            <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as typeof sortKey)}
              className="bg-transparent text-xs focus:outline-none"
              title="Sort by"
            >
              <option value="username">Username</option>
              <option value="file_count">Files</option>
              <option value="size_bytes">Size</option>
              <option value="mtime">Last update</option>
              <option value="ctime">Theo thời gian tạo</option>
            </select>
            <button
              onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              className="ml-1 p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-foreground"
              title={`Sort ${sortDir === "asc" ? "ascending" : "descending"} — click to toggle`}
            >
              <span className="text-xs font-mono">{sortDir === "asc" ? "↑" : "↓"}</span>
            </button>
          </div>
        </div>

        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground flex-wrap">
          <span className="px-2 py-0.5 rounded-full bg-pink-500/15 text-pink-200 font-mono">{formatNumber(stats.ig)} Instagram</span>
          <span className="px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-200 font-mono">{formatNumber(stats.tw)} Twitter / X</span>
          {debounced && <span>filtered: {filtered.length} / {stats.total}</span>}
        </div>
      </Card>

      {/* Grid */}
      {isLoading ? (
        <Card variant="glass" className="p-12 text-center text-muted-foreground">Loading accounts…</Card>
      ) : filtered.length === 0 ? (
        <Card variant="glass" className="p-12 text-center text-muted-foreground">
          {stats.total === 0
            ? "No instagram/ or twitter/ folder under E:\\gallery-dl yet. Run a download first."
            : "No accounts match your search."}
        </Card>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {filtered.map((a, i) => <AccountGridCard key={`${a.platform}:${a.username}`} a={a} delay={i} />)}
        </div>
      ) : (
        <Card variant="glass">
          <CardContent className="p-0">
            <div className="hidden md:grid grid-cols-[2.5rem_1fr_auto_auto_auto_auto] gap-3 items-center px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5 font-mono">
              <span></span>
              <span>username</span>
              <span className="text-right">files</span>
              <span className="text-right">size</span>
              <span className="text-right">img / vid</span>
              <span className="text-right">{sortKey === "mtime" ? "updated ↓" : sortKey === "ctime" ? "created ↓" : "last seen"}</span>
            </div>
            <div className="divide-y divide-white/5 max-h-[70vh] overflow-y-auto">
              {filtered.map((a, i) => <AccountRow key={`${a.platform}:${a.username}`} a={a} delay={i} sortKey={sortKey} />)}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function platformAccent(p: AccountCard["platform"]): string {
  return p === "instagram"
    ? "from-pink-500/30 to-amber-400/20 text-pink-200"
    : "from-sky-500/30 to-blue-500/20 text-sky-200";
}

function AccountGridCard({ a, delay }: { a: AccountCard; delay: number }) {
  const initial = a.username.replace(/^@/, "").charAt(0).toUpperCase() || "?";
  return (
    <Link
      href={`/gallery?path=${encodeURIComponent(a.rel_path)}`}
      className="group relative overflow-hidden rounded-lg border border-white/5 bg-card/40 hover:border-primary/40 transition-all hover:-translate-y-0.5 fade-in-up"
      style={{ animationDelay: `${Math.min(delay, 12) * 20}ms` }}
      title={`Open @${a.username} in Gallery`}
    >
      <div className={cn("aspect-square bg-gradient-to-br flex items-center justify-center relative overflow-hidden", platformAccent(a.platform))}>
        <div className="text-4xl font-bold opacity-80 group-hover:scale-110 transition-transform">
          {initial}
        </div>
        <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/60 backdrop-blur">
          {a.platform === "instagram" ? "IG" : "TW"}
        </div>
        <div className="absolute top-1 right-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-black/60 backdrop-blur">
          {formatNumber(a.file_count)} f
        </div>
      </div>
      <div className="p-2 space-y-0.5">
        <div className="text-xs font-medium truncate" title={a.username}>@{a.username}</div>
        <div className="text-[10px] text-muted-foreground font-mono flex items-center justify-between">
          <span>{formatBytes(a.size_bytes)}</span>
          <span>{a.folder_count > 0 ? `${a.folder_count}f` : ""}</span>
        </div>
        <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-1.5">
          {a.image_count > 0 && <span className="text-primary/80">▣ {formatNumber(a.image_count)}</span>}
          {a.video_count > 0 && <span className="text-accent/80">▶ {formatNumber(a.video_count)}</span>}
          {a.mtime > 0 && <span className="ml-auto">{new Date(a.mtime * 1000).toLocaleDateString()}</span>}
        </div>
      </div>
      <ExternalLink className="absolute bottom-2 right-2 h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
    </Link>
  );
}

function AccountRow({ a, delay, sortKey }: { a: AccountCard; delay: number; sortKey: string }) {
  const ts = sortKey === "ctime" ? (a.ctime ?? 0) : a.mtime;
  return (
    <Link
      href={`/gallery?path=${encodeURIComponent(a.rel_path)}`}
      className={cn(
        "grid grid-cols-[2.5rem_1fr_auto_auto_auto_auto] gap-3 items-center p-3 hover:bg-white/5 transition-colors text-left fade-in-up",
      )}
      style={{ animationDelay: `${Math.min(delay, 12) * 15}ms` }}
      title={`Open @${a.username} in Gallery`}
    >
      <div className={cn("h-8 w-8 rounded-md flex items-center justify-center bg-gradient-to-br font-bold text-sm", platformAccent(a.platform))}>
        {a.username.replace(/^@/, "").charAt(0).toUpperCase() || "?"}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium truncate">@{a.username}</div>
        <div className="text-[11px] text-muted-foreground font-mono truncate">
          {a.platform === "instagram" ? "Instagram" : "Twitter / X"} · {a.rel_path}
        </div>
      </div>
      <div className="text-xs text-muted-foreground text-right font-mono shrink-0">{formatNumber(a.file_count)}</div>
      <div className="text-xs text-muted-foreground text-right font-mono shrink-0 w-20">{formatBytes(a.size_bytes)}</div>
      <div className="text-xs text-muted-foreground text-right font-mono shrink-0 w-24 hidden md:block">
        {a.image_count > 0 && <span className="text-primary/80 mr-2">▣{a.image_count}</span>}
        {a.video_count > 0 && <span className="text-accent/80">▶{a.video_count}</span>}
      </div>
      <div className="text-xs text-muted-foreground text-right font-mono shrink-0 w-24">
        {ts ? new Date(ts * 1000).toLocaleDateString() : "—"}
      </div>
    </Link>
  );
}
