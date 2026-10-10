"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DownloadPlatform, type DownloadSource, type DownloadStats, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StatCards } from "@/components/StatCards";
import { useSystemWebSocket, type LogEvent } from "@/lib/websocket";
import {
  Instagram, Twitter, Link2, ListTree, Database, Loader2,
  Sparkles, Plus, CheckCircle2, XCircle, Clock, Download as DownloadIcon,
  TrendingUp, Terminal, Trash2, Pause, Play, Square, Music2,
} from "lucide-react";
import { toast } from "sonner";
import { cn, formatBytes, formatDuration } from "@/lib/utils";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <Header />
      <StatCards />
      <DownloadConsole />
      <ActiveJobIndicator />
      <DownloadQueueSummary />
      <LiveTerminal />
    </div>
  );
}

// =========================================================================
// Header
// =========================================================================
function Header() {
  return (
    <div className="flex items-end justify-between flex-wrap gap-4">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">Dashboard</span>
        </h2>
        <p className="text-muted-foreground mt-1 flex items-center gap-2 text-sm">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          Queue & monitor downloads across Instagram, Twitter / X and TikTok
        </p>
      </div>
      <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-success" />
        </span>
        <span>Live · WebSocket connected</span>
      </div>
    </div>
  );
}

// =========================================================================
// Download Console — 2 lớp: platform tabs + source radio (ảnh 1 + ảnh 2)
// =========================================================================

const PLATFORMS: { value: DownloadPlatform; label: string; icon: typeof Instagram; gradient: string; hint: string }[] = [
  { value: "instagram", label: "Instagram", icon: Instagram, gradient: "from-[#f09433] via-[#e6683c] via-[#dc2743] via-[#cc2366] to-[#bc1888]", hint: "Posts · Stories · Highlights" },
  { value: "twitter", label: "Twitter / X", icon: Twitter, gradient: "from-[#1da1f2] via-[#0a85d0] to-black", hint: "Tweets · Videos · Spaces" },
  { value: "tiktok", label: "TikTok", icon: Music2, gradient: "from-[#25f4ee] via-[#25f4ee] to-[#fe2c55] to-[#000]", hint: "Videos · User feed" },
];

const SOURCES: { value: DownloadSource; label: string; desc: string; icon: typeof Link2 }[] = [
  { value: "link", label: "Single link", desc: "One post / tweet URL", icon: Link2 },
  { value: "list", label: "Bulk list", desc: "Many URLs, one per line", icon: ListTree },
  { value: "database", label: "From database", desc: "Pick existing accounts", icon: Database },
];

// Host used when rebuilding a profile URL from a database account.
const PLATFORM_HOST: Record<DownloadPlatform, string> = {
  instagram: "instagram.com",
  twitter: "twitter.com",
  tiktok: "www.tiktok.com",
};

const PLACEHOLDER_LINK: Record<DownloadPlatform, string> = {
  instagram: "https://instagram.com/p/ABC123/",
  twitter: "https://x.com/user/status/123",
  tiktok: "https://www.tiktok.com/@username  ·  https://www.tiktok.com/@username/video/123",
};

const PLACEHOLDER_LIST: Record<DownloadPlatform, string> = {
  instagram: "https://instagram.com/p/ABC1\nhttps://instagram.com/p/ABC2\nhttps://instagram.com/user1",
  twitter: "https://x.com/u1/status/1\nhttps://x.com/u2/status/2\nhttps://x.com/user3",
  tiktok: "https://www.tiktok.com/@user1\nhttps://www.tiktok.com/@user2/video/7123456789\nvm.tiktok.com/ZMabc123/",
};

function DownloadConsole() {
  const [platform, setPlatform] = useState<DownloadPlatform>("instagram");
  const [source, setSource] = useState<DownloadSource>("link");
  const [text, setText] = useState("");
  const [selectedAccounts, setSelectedAccounts] = useState<number[]>([]);
  // Per-layer checkboxes — when source = "list" or "database" + platform=IG,
  // these decide which 1-3 download rows get created. For X they're ignored
  // (we always create a single "tweet" row + auto-detect live).
  const [layerPosts, setLayerPosts] = useState(true);
  const [layerStories, setLayerStories] = useState(false);
  const [layerHighlights, setLayerHighlights] = useState(false);
  const qc = useQueryClient();

  // TikTok has no account table yet (the `accounts` API only mirrors the
  // instagram/ and twitter/ folders), so the "From database" source is hidden.
  useEffect(() => {
    if (platform === "tiktok" && source === "database") setSource("link");
  }, [platform, source]);

  // Load accounts for "From database" source
  const { data: accountsData } = useQuery({
    queryKey: ["accounts-all"],
    queryFn: async () =>
      (await api.get("/api/accounts", { params: { page: 1, page_size: 200 } })).data,
    enabled: source === "database",
  });

  const batchMut = useMutation({
    mutationFn: async (payload: { platform: DownloadPlatform; source_type: DownloadSource; items: any[] }) =>
      (await api.post("/api/downloads/batch", payload)).data,
    onSuccess: (res) => {
      toast.success(`Added ${res.created} to queue`);
      setText("");
      setSelectedAccounts([]);
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["downloads-stats"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed to add"),
  });

  const runMut = useMutation({
    mutationFn: async (plat: DownloadPlatform) =>
      (await api.post("/api/downloads/run-pending", null, { params: { platform: plat } })).data,
    onSuccess: (res) => {
      toast.success(`Marked ${res.marked} downloads as in-progress`);
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
  });  function parseLinks(): { url: string; author?: string }[] {
    // Derive the author so the backend can locate the output folder without a
    // second guess. TikTok always carries "@name"; IG / X do not, so for those
    // the author is the segment before the trailing post/status id.
    const authorOf = (u: string) => {
      const at = u.match(/@([\w_.-]+)/)?.[1];
      if (at) return at;
      const segs = u.split("/").filter(Boolean);
      const host = segs[0]?.replace(/^www\./, "");
      const rest = segs.slice(1);
      if (!rest.length) return host;
      // IG post /p/CODE → segs[-2] is the author; X /user/status/ID → segs[-3].
      return rest.length >= 3 ? rest[rest.length - 3] : rest[rest.length - 2];
    };

    if (source === "link") {
      const u = text.trim();
      if (!u) return [];
      return [{ url: u, author: authorOf(u) }];
    }
    if (source === "list") {
      return text
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .map((u) => ({ url: u, author: authorOf(u) }));
    }
    return [];
  }

  function addToQueue() {
    if (source === "database") {
      if (selectedAccounts.length === 0) {
        toast.error("Pick at least one account");
        return;
      }
      const accts = (accountsData?.items || []).filter((a: any) => selectedAccounts.includes(a.id));
      // For IG: emit 1 row per selected layer per account. For X: 1 row per account.
      const items: any[] = [];
      for (const a of accts) {
        const base = `https://${PLATFORM_HOST[platform]}/${a.username}`;
        if (platform === "instagram") {
          if (layerPosts)      items.push({ url: base, author: a.username, account_id: a.id, content_type: "post" });
          if (layerStories)    items.push({ url: base, author: a.username, account_id: a.id, content_type: "story" });
          if (layerHighlights) items.push({ url: base, author: a.username, account_id: a.id, content_type: "highlight" });
        } else {
          items.push({ url: base, author: a.username, account_id: a.id, content_type: "tweet" });
        }
      }
      if (items.length === 0) {
        toast.error("Pick at least one content type");
        return;
      }
      batchMut.mutate({ platform, source_type: source, items });
    } else {
      const items = parseLinks();
      if (items.length === 0) {
        toast.error("Paste at least one URL");
        return;
      }
      // For IG "link" source: the same URL can be downloaded as post / story /
      // highlight — emit one row per selected layer so the user gets the
      // full set in one queue action.
      if (platform === "instagram") {
        const expanded: any[] = [];
        for (const it of items) {
          if (layerPosts)      expanded.push({ ...it, content_type: "post" });
          if (layerStories)    expanded.push({ ...it, content_type: "story" });
          if (layerHighlights) expanded.push({ ...it, content_type: "highlight" });
        }
        if (expanded.length === 0) {
          toast.error("Pick at least one content type");
          return;
        }
        batchMut.mutate({ platform, source_type: source, items: expanded });
      } else if (platform === "tiktok") {
        // TikTok has a single media kind — the URL shape decides whether
        // gallery-dl pulls one video or the whole user feed.
        batchMut.mutate({
          platform, source_type: source,
          items: items.map((it) => ({ ...it, content_type: "tiktok" })),
        });
      } else {
        // X — tag every item as "tweet"; the service auto-detects live URLs.
        batchMut.mutate({
          platform, source_type: source,
          items: items.map((it) => ({ ...it, content_type: "tweet" })),
        });
      }
    }
  }

  return (
    <Card variant="gradient" className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-lg flex items-center gap-2">
            <Plus className="h-5 w-5 text-primary" /> Add to download queue
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => runMut.mutate(platform)}
            disabled={runMut.isPending}
            className="gap-2"
          >
            {runMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <DownloadIcon className="h-3.5 w-3.5" />}
            Run pending ({platform})
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* ----- Layer 1: platform tabs ----- */}
        <div className="grid grid-cols-3 gap-3">
          {PLATFORMS.map((p) => {
            const Icon = p.icon;
            const active = platform === p.value;
            return (
              <button
                key={p.value}
                onClick={() => setPlatform(p.value)}
                className={cn(
                  "relative overflow-hidden rounded-xl border p-4 text-left transition-all",
                  active
                    ? "border-white/20 shadow-glow-sm"
                    : "border-white/5 hover:border-white/10 opacity-70 hover:opacity-100"
                )}
              >
                <div
                  className={cn(
                    "absolute inset-0 bg-gradient-to-br opacity-30 transition-opacity",
                    p.gradient,
                    active && "opacity-60"
                  )}
                />
                <div className="relative flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 backdrop-blur">
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <div>
                    <div className="font-semibold text-white">{p.label}</div>
                    <div className="text-xs text-white/70">
                      {p.hint}
                    </div>
                  </div>
                  {active && (
                    <CheckCircle2 className="absolute right-3 top-3 h-4 w-4 text-white" />
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* ----- Layer 2: source radio ----- */}
        <div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Input source
          </div>
          <div className={cn("grid gap-2", platform === "tiktok" ? "grid-cols-2" : "grid-cols-3")}>
            {SOURCES.filter((s) => s.value !== "database" || platform !== "tiktok").map((s) => {
              const Icon = s.icon;
              const active = source === s.value;
              return (
                <button
                  key={s.value}
                  onClick={() => setSource(s.value)}
                  className={cn(
                    "flex flex-col items-start gap-1.5 rounded-lg border p-3 text-left transition-all",
                    active
                      ? "border-primary/40 bg-primary/10 shadow-glow-sm"
                      : "border-white/5 bg-card/40 hover:border-white/10 hover:bg-white/5"
                  )}
                >
                  <div className="flex items-center gap-2 w-full">
                    <div className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-md",
                      active ? "bg-primary/20 text-primary" : "bg-white/5 text-muted-foreground"
                    )}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <div className="text-sm font-medium">{s.label}</div>
                  </div>
                  <div className="text-[10px] text-muted-foreground">{s.desc}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ----- Layer 2.5: IG content-type checkboxes (only for IG) ----- */}
        {platform === "instagram" && (
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              What to download (Instagram)
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { key: "posts", label: "Posts", desc: "Timeline feed", value: layerPosts, set: setLayerPosts, accent: "from-[#f09433] to-[#dc2743]" },
                { key: "stories", label: "Stories", desc: "24h expiring", value: layerStories, set: setLayerStories, accent: "from-[#833ab4] to-[#fd1d1d]" },
                { key: "highlights", label: "Highlights", desc: "Permanent reels", value: layerHighlights, set: setLayerHighlights, accent: "from-[#fcb045] to-[#fd1d1d]" },
              ].map((opt) => {
                const active = opt.value;
                return (
                  <button
                    key={opt.key}
                    onClick={() => opt.set(!opt.value)}
                    className={cn(
                      "flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-all",
                      active
                        ? "border-primary/40 bg-primary/10 shadow-glow-sm"
                        : "border-white/5 bg-card/40 hover:border-white/10 hover:bg-white/5"
                    )}
                  >
                    <div className="flex items-center gap-2 w-full">
                      <div className={cn(
                        "flex h-4 w-4 items-center justify-center rounded border transition-colors",
                        active ? "bg-gradient-to-br border-transparent text-white" : "border-white/30 bg-white/5",
                        opt.accent
                      )}>
                        {active && <CheckCircle2 className="h-3 w-3" />}
                      </div>
                      <div className="text-sm font-medium">{opt.label}</div>
                    </div>
                    <div className="text-[10px] text-muted-foreground pl-6">{opt.desc}</div>
                  </button>
                );
              })}
            </div>
            <div className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1">
              <span>Tip: split into separate runs to avoid IG rate-limits</span>
            </div>
          </div>
        )}

        {/* ----- Layer 3: input by source ----- */}
        {source === "link" && (
          <div>
            <Input
              placeholder={PLACEHOLDER_LINK[platform]}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="bg-background/50 font-mono text-xs"
            />
          </div>
        )}
        {source === "list" && (
          <div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              placeholder={PLACEHOLDER_LIST[platform]}
              className="w-full rounded-md border border-input bg-background/50 px-3 py-2 text-xs font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <div className="text-[10px] text-muted-foreground mt-1">
              {text.split(/\r?\n/).filter((l) => l.trim()).length} URL(s) detected
            </div>
          </div>
        )}
        {source === "database" && (
          <div className="rounded-lg border border-white/5 bg-background/30 p-3 max-h-64 overflow-y-auto space-y-1">
            {!accountsData ? (
              <div className="text-xs text-muted-foreground flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading accounts...
              </div>
            ) : (accountsData.items || []).length === 0 ? (
              <div className="text-xs text-muted-foreground">No accounts in database yet</div>
            ) : (
              accountsData.items.map((a: any) => {
                const checked = selectedAccounts.includes(a.id);
                return (
                  <label
                    key={a.id}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-white/5 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedAccounts((s) => [...s, a.id]);
                        else setSelectedAccounts((s) => s.filter((x) => x !== a.id));
                      }}
                      className="accent-primary"
                    />
                    <div className="h-6 w-6 rounded-full bg-gradient-to-br from-primary/40 to-accent/40 flex items-center justify-center text-[10px] font-bold">
                      {a.username.charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm">@{a.username}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">
                        {a.total_posts} posts · {a.total_stories} stories
                      </div>
                    </div>
                  </label>
                );
              })
            )}
          </div>
        )}

        <Button
          onClick={addToQueue}
          disabled={batchMut.isPending}
          className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90 text-white shadow-glow-sm"
        >
          {batchMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Add to queue
        </Button>
      </CardContent>
    </Card>
  );
}

// =========================================================================
// Active job indicator — Stop button + Resume/Run-pending call-to-action
// =========================================================================

interface PendingSummary {
  platform: string;
  pending: number;
  in_flight: number;
  resumable: number;
}

function ActiveJobIndicator() {
  const qc = useQueryClient();
  const { data: activeData } = useQuery<{ job: Job | null }>({
    queryKey: ["active-job"],
    queryFn: async () => (await api.get("/api/jobs/active")).data,
    refetchInterval: 3_000,
  });
  const job = activeData?.job ?? null;
  const [elapsed, setElapsed] = useState(0);

  // Per-platform pending summary — used to render "Resume pending (N)" chips
  const summaries = useQuery<Record<string, PendingSummary>>({
    queryKey: ["pending-summary-all"],
    queryFn: async () => {
      const [ig, tw, tt] = await Promise.all(
        (["instagram", "twitter", "tiktok"] as const).map((p) =>
          api.get("/api/downloads/pending-summary", { params: { platform: p } })
        )
      );
      return { instagram: ig.data, twitter: tw.data, tiktok: tt.data };
    },
    refetchInterval: 5_000,
  });

  useEffect(() => {
    if (!job?.started_at) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - new Date(job.started_at!).getTime()) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [job?.started_at]);

  const stopMut = useMutation({
    mutationFn: async (jobId: number) => (await api.post(`/api/jobs/${jobId}/stop`)).data,
    onSuccess: () => {
      toast.success("Stop signal sent — current download will finish or be torn down");
      qc.invalidateQueries({ queryKey: ["active-job"] });
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["downloads-stats"] });
      qc.invalidateQueries({ queryKey: ["pending-summary-all"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed to stop"),
  });

  const runMut = useMutation({
    mutationFn: async (plat: DownloadPlatform) =>
      (await api.post("/api/downloads/run-pending", null, { params: { platform: plat } })).data,
    onSuccess: (res) => {
      if (res.marked === 0) {
        toast.info(`No pending ${res.job_id ? "" : ""}downloads for ${res.platform ?? "this platform"}`);
      } else {
        toast.success(`Resumed ${res.marked} pending download${res.marked === 1 ? "" : "s"}`);
      }
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["active-job"] });
      qc.invalidateQueries({ queryKey: ["pending-summary-all"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed to resume"),
  });

  const ig = summaries.data?.instagram;
  const tw = summaries.data?.twitter;
  const tt = summaries.data?.tiktok;
  const totalResumable = (ig?.resumable ?? 0) + (tw?.resumable ?? 0) + (tt?.resumable ?? 0);

  return (
    <Card variant="gradient" className="overflow-hidden">
      <CardContent className="p-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* ----- Left: active job status ----- */}
          <div className="rounded-xl border border-white/5 bg-background/30 p-4">
            {job ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="relative flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent" />
                  </div>
                  <span className="text-sm font-semibold">Job <span className="font-mono text-primary">#{job.id}</span> is running</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider bg-accent/15 text-accent">
                    {job.status}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-lg border border-white/5 bg-black/30 p-2">
                    <div className="text-xl font-bold text-accent">{formatDuration(elapsed)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Elapsed</div>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-black/30 p-2">
                    <div className="text-xl font-bold">{job.new_files_count}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">New files</div>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-black/30 p-2">
                    <div className="text-xl font-bold">{job.total_processed}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Processed</div>
                  </div>
                </div>
                <div className="text-[11px] text-muted-foreground line-clamp-2 break-all font-mono">
                  {job.targets ? JSON.parse(job.targets).slice(0, 3).join(", ") + (JSON.parse(job.targets).length > 3 ? "…" : "") : ""}
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => stopMut.mutate(job.id)}
                  disabled={stopMut.isPending}
                  className="w-full gap-2"
                >
                  {stopMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  Dừng & lưu tiến trình (Stop)
                </Button>
                <div className="text-[10px] text-muted-foreground text-center">
                  Stop sẽ ngắt subprocess hiện tại và reset tất cả mục đang chạy về <span className="font-mono text-warning">pending</span> để bạn có thể resume.
                </div>
              </div>
            ) : (
              <div className="space-y-3 py-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
                  <span>Không có job nào đang chạy</span>
                </div>
                {totalResumable > 0 ? (
                  <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-warning space-y-1">
                    <div className="font-semibold">Có {totalResumable} mục chưa hoàn thành</div>
                    <div className="text-warning/80 text-[11px]">
                      Bấm nút <span className="font-mono">Resume</span> bên dưới để tiếp tục từ nơi đã dừng. Hệ thống sẽ tự động bỏ qua file đã tải nhờ archive sqlite.
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-muted-foreground">
                    Thêm URL ở console bên trên, hoặc bấm <span className="font-mono">Run pending</span> để chạy các mục đang chờ.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ----- Right: per-platform resume chips ----- */}
          <div className="rounded-xl border border-white/5 bg-background/30 p-4 space-y-3">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Resume pending theo nền tảng
            </div>
            <ResumeRow
              platform="instagram"
              label="Instagram"
              icon={Instagram}
              gradient="from-[#f09433] via-[#e6683c] to-[#bc1888]"
              summary={ig}
              running={!!job?.targets?.includes("instagram.com")}
              isPending={runMut.isPending && runMut.variables === "instagram"}
              onResume={() => runMut.mutate("instagram")}
            />
            <ResumeRow
              platform="twitter"
              label="Twitter / X"
              icon={Twitter}
              gradient="from-[#1da1f2] via-[#0a85d0] to-black"
              summary={tw}
              running={!!job?.targets?.includes("twitter.com")}
              isPending={runMut.isPending && runMut.variables === "twitter"}
              onResume={() => runMut.mutate("twitter")}
            />
            <ResumeRow
              platform="tiktok"
              label="TikTok"
              icon={Music2}
              gradient="from-[#25f4ee] via-[#25f4ee] to-[#fe2c55]"
              summary={tt}
              running={!!job?.targets?.includes("tiktok.com")}
              isPending={runMut.isPending && runMut.variables === "tiktok"}
              onResume={() => runMut.mutate("tiktok")}
            />
            <div className="text-[10px] text-muted-foreground pt-1 border-t border-white/5">
              <span className="font-mono text-warning">pending</span> = sẵn sàng tải ·
              <span className="font-mono text-accent"> in_flight</span> = đang chạy (sẽ tự reset về pending khi job kết thúc / crash).
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ResumeRow({
  platform, label, icon: Icon, gradient, summary, running, isPending, onResume,
}: {
  platform: DownloadPlatform;
  label: string;
  icon: typeof Instagram;
  gradient: string;
  summary: PendingSummary | undefined;
  running: boolean;
  isPending: boolean;
  onResume: () => void;
}) {
  const resumable = summary?.resumable ?? 0;
  const disabled = running || resumable === 0 || isPending;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-black/20 p-2.5">
      <div className={cn("flex h-9 w-9 items-center justify-center rounded-md bg-gradient-to-br", gradient)}>
        <Icon className="h-4 w-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium flex items-center gap-2">
          {label}
          {running && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider bg-accent/15 text-accent flex items-center gap-1">
              <Loader2 className="h-2.5 w-2.5 animate-spin" /> running
            </span>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-2 flex-wrap">
          <span><span className="text-warning">{summary?.pending ?? 0}</span> pending</span>
          <span className="text-muted-foreground/50">·</span>
          <span><span className="text-accent">{summary?.in_flight ?? 0}</span> in_flight</span>
          <span className="text-muted-foreground/50">·</span>
          <span className="text-foreground font-semibold">{resumable} resumable</span>
        </div>
      </div>
      <Button
        size="sm"
        variant={resumable > 0 ? "default" : "outline"}
        onClick={onResume}
        disabled={disabled}
        className={cn(
          "gap-1.5 min-w-[110px]",
          resumable > 0 && !running && "bg-gradient-to-r from-primary to-accent hover:opacity-90 text-white shadow-glow-sm"
        )}
      >
        {isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
        {running ? "Đang chạy" : resumable === 0 ? "Hết hàng" : `Resume (${resumable})`}
      </Button>
    </div>
  );
}

// =========================================================================
// Queue summary
// =========================================================================
function DownloadQueueSummary() {
  const { data: stats } = useQuery<DownloadStats>({
    queryKey: ["downloads-stats"],
    queryFn: async () => (await api.get("/api/downloads/stats")).data,
    refetchInterval: 5_000,
  });

  if (!stats) return null;

  const platEntries = Object.entries(stats.by_platform);
  const statusEntries = Object.entries(stats.by_status);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" /> Queue by platform
          </CardTitle>
        </CardHeader>
        <CardContent>
          {platEntries.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center">No downloads yet</div>
          ) : (
            <div className="space-y-3">
              {platEntries.map(([p, n]) => (
                <PlatformBar
                  key={p}
                  platform={p as DownloadPlatform}
                  count={n}
                  max={Math.max(...platEntries.map(([_, v]) => v), 1)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4 text-accent" /> Status breakdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          {statusEntries.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center">No downloads yet</div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {statusEntries.map(([s, n]) => (
                <StatusPill key={s} status={s} count={n} />
              ))}
            </div>
          )}
          <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="text-xl font-bold">{stats.last_24h}</div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Last 24h</div>
            </div>
            <div>
              <div className="text-xl font-bold">{stats.last_7d}</div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Last 7d</div>
            </div>
            <div>
              <div className="text-xl font-bold">{formatBytes(stats.total_size_bytes)}</div>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Total size</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PlatformBar({ platform, count, max }: { platform: DownloadPlatform; count: number; max: number }) {
  const cfg = PLATFORMS.find((p) => p.value === platform)!;
  const Icon = cfg.icon;
  const pct = Math.round((count / max) * 100);
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5" />
          <span className="text-sm font-medium">{cfg.label}</span>
        </div>
        <span className="text-xs font-mono text-muted-foreground">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
        <div
          className={cn("h-full bg-gradient-to-r transition-all", cfg.gradient)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const STATUS_META: Record<string, { icon: typeof Clock; color: string; label: string }> = {
  pending: { icon: Clock, color: "text-warning bg-warning/10", label: "Pending" },
  downloading: { icon: Loader2, color: "text-accent bg-accent/10", label: "Downloading" },
  completed: { icon: CheckCircle2, color: "text-success bg-success/10", label: "Completed" },
  failed: { icon: XCircle, color: "text-destructive bg-destructive/10", label: "Failed" },
  skipped: { icon: XCircle, color: "text-muted-foreground bg-muted", label: "Skipped" },
};

function StatusPill({ status, count }: { status: string; count: number }) {
  const meta = STATUS_META[status] || { icon: Clock, color: "text-muted-foreground bg-muted", label: status };
  const Icon = meta.icon;
  return (
    <div className={cn("flex items-center gap-2 rounded-lg px-3 py-2", meta.color)}>
      <Icon className={cn("h-4 w-4", status === "downloading" && "animate-spin")} />
      <div>
        <div className="text-sm font-bold">{count}</div>
        <div className="text-[10px] opacity-80">{meta.label}</div>
      </div>
    </div>
  );
}

// =========================================================================
// Live terminal — real-time log panel for whatever the runner is doing
// =========================================================================

const MAX_LINES = 500;

function classifyLogLine(line: string): { tone: "info" | "success" | "warn" | "error" | "muted"; label?: string } {
  const l = line.toLowerCase();
  if (!line.trim()) return { tone: "muted" };
  if (l.includes("[error]") || l.includes("error:") || l.includes("exception") || l.includes("failed") || l.includes("exit code")) {
    return { tone: "error" };
  }
  if (l.includes("warn") || l.includes("rate limit") || l.includes("429") || l.includes("rate-limit")) {
    return { tone: "warn" };
  }
  if (l.includes("done ") || l.includes("completed") || l.includes("media:") || l.includes("new=") || l.includes("user_done")) {
    return { tone: "success" };
  }
  if (l.startsWith("-->") || l.startsWith("done") || l.includes("downloading") || l.includes("launching")) {
    return { tone: "info" };
  }
  return { tone: "muted" };
}

const TONE_CLS: Record<string, string> = {
  info: "text-zinc-100",
  success: "text-emerald-300",
  warn: "text-amber-300",
  error: "text-rose-300",
  muted: "text-zinc-500",
};

function LiveTerminal() {
  const containerRef = useRef<HTMLDivElement>(null);
  const linesRef = useRef<{ ts: number; text: string }[]>([]);
  const [lineCount, setLineCount] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState<"all" | "info" | "success" | "warn" | "error">("all");
  const [elapsed, setElapsed] = useState(0);
  const qc = useQueryClient();

  // Which job are we currently following? Auto-detect the active one.
  const { data: activeData } = useQuery<{ job: Job | null }>({
    queryKey: ["active-job"],
    queryFn: async () => (await api.get("/api/jobs/active")).data,
    refetchInterval: 3_000,
  });
  const job = activeData?.job ?? null;

  // Tick the elapsed-time clock every second while a job is running.
  useEffect(() => {
    if (!job?.started_at) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - new Date(job.started_at!).getTime()) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [job?.started_at]);

  // WebSocket — follow the active job if any, else listen to /ws/system for
  // download_update / job_update notifications (so the panel still shows
  // "no active job" lines when the runner is idle).
  const { connected, resetCursor } = useSystemWebSocket((event: LogEvent) => {
    if (event.type === "log") {
      const text: string = event.data?.message ?? "";
      if (!text) return;
      linesRef.current.push({ ts: Date.now(), text });
      if (linesRef.current.length > MAX_LINES) {
        linesRef.current = linesRef.current.slice(-MAX_LINES);
      }
      setLineCount(linesRef.current.length);
      scrollToBottom();
    } else if (event.type === "job_update" || event.type === "status") {
      // refresh active job so the header pill updates
      qc.invalidateQueries({ queryKey: ["active-job"] });
      // also reflect job-level events into the log so the user sees them
      const id = event.data?.job_id;
      const status = event.data?.status;
      const new_files = event.data?.new_files;
      const processed = event.data?.processed;
      const platform = event.data?.platform;
      if (id && status) {
        const note = new_files != null
          ? `JOB #${id} ${status} · platform=${platform ?? "?"} · new_files=${new_files} · processed=${processed ?? 0}`
          : `JOB #${id} ${status}`;
        linesRef.current.push({ ts: Date.now(), text: note });
        if (linesRef.current.length > MAX_LINES) {
          linesRef.current = linesRef.current.slice(-MAX_LINES);
        }
        setLineCount(linesRef.current.length);
        scrollToBottom();
      }
    }
  });

  function scrollToBottom() {
    if (!autoScroll || !containerRef.current) return;
    requestAnimationFrame(() => {
      if (!containerRef.current) return;
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    });
  }

  function handleScroll() {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    setAutoScroll(atBottom);
  }

  function clear() {
    linesRef.current = [];
    setLineCount(0);
    // Reset the polling cursor so the next poll re-fetches everything
    // (useful right after clearing to see the same events again).
    resetCursor();
  }

  // Filter view (does not mutate the underlying buffer)
  const visible = (filter === "all"
    ? linesRef.current
    : linesRef.current.filter((l) => classifyLogLine(l.text).tone === filter)
  ).slice(-MAX_LINES);

  return (
    <Card variant="glass" className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-3 flex-wrap pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/20">
            <Terminal className="h-4 w-4 text-primary" />
          </div>
          <CardTitle className="text-base flex items-center gap-2">
            Live terminal
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider",
              connected === "live" && "bg-success/15 text-success",
              connected === "polling" && "bg-amber-500/15 text-amber-300",
              connected === "connecting" && "bg-muted text-muted-foreground",
              connected === "offline" && "bg-rose-500/15 text-rose-300"
            )}>
              {connected === "live" && "● live"}
              {connected === "polling" && "◐ polling"}
              {connected === "connecting" && "○ connecting"}
              {connected === "offline" && "○ offline"}
            </span>
          </CardTitle>
          {job ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground ml-2">
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
              <span>Job <span className="font-mono text-primary">#{job.id}</span></span>
              <span>·</span>
              <span className="font-mono">{job.new_files_count} new</span>
              <span>·</span>
              <span className="font-mono">{formatDuration(elapsed)}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground ml-2">
              <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
              <span>No active job</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {(["all", "info", "success", "warn", "error"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-2 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors",
                filter === f
                  ? "bg-white/10 text-foreground border border-white/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/5"
              )}
            >
              {f}
            </button>
          ))}
          <div className="w-px h-5 bg-white/10 mx-1" />
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setAutoScroll((v) => !v)}
            title={autoScroll ? "Pause auto-scroll" : "Resume auto-scroll"}
          >
            {autoScroll ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={clear}
            title="Clear buffer"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="px-3 py-1.5 text-[10px] text-muted-foreground border-y border-white/5 bg-black/30 flex items-center justify-between">
          <span className="font-mono">
            {lineCount === 0
              ? "Waiting for events… (run a job from the console above)"
              : `${lineCount} line${lineCount === 1 ? "" : "s"} in buffer · showing ${visible.length}`}
          </span>
          {!autoScroll && (
            <button
              onClick={scrollToBottom}
              className="text-primary hover:underline flex items-center gap-1"
            >
              <Square className="h-2.5 w-2.5 fill-primary" /> Jump to latest
            </button>
          )}
        </div>
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-[420px] overflow-y-auto bg-black p-3 font-mono text-[11px] leading-5"
        >
          {visible.length === 0 ? (
            <div className="text-zinc-600 italic">
              {lineCount === 0
                ? "▌ no events yet — start a job above to see live output"
                : "▌ no lines match the current filter"}
            </div>
          ) : (
            visible.map((l, i) => {
              const { tone } = classifyLogLine(l.text);
              return (
                <div key={i} className="flex gap-2 hover:bg-white/[0.03] -mx-3 px-3">
                  <span className="text-zinc-600 select-none w-16 flex-shrink-0">
                    {new Date(l.ts).toLocaleTimeString("en-GB", { hour12: false })}
                  </span>
                  <span className={cn("whitespace-pre-wrap break-all", TONE_CLS[tone])}>
                    {l.text}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}
