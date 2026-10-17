"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DownloadPlatform, type DownloadSource, type DownloadStats, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StatCards } from "@/components/StatCards";
import { PageHeader } from "@/components/PageHeader";
import { PlatformDot } from "@/components/PlatformDot";
import { ShortcutChip } from "@/components/ShortcutChip";
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
      <PageHeader
        title="Dashboard"
        description="Theo dõi và xếp hàng tải từ Instagram, X và TikTok"
        actions={
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("dnload:quick-add"))}
            className="flex items-center gap-2 rounded-md border border-border bg-surface-1 px-3 py-1.5 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Thêm nhanh <ShortcutChip>⌘K</ShortcutChip>
          </button>
        }
      />
      <StatCards />
      <DownloadConsole />
      <ActiveJobIndicator />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DownloadQueueSummary />
        <LiveTerminal />
      </div>
    </div>
  );
}

// =========================================================================
// Download Console — 2 lớp: platform tabs + source radio (ảnh 1 + ảnh 2)
// =========================================================================

// Platform configuration. The `mono` flag is the only platform-specific
// signal now — active tab uses `bg-foreground text-background` (high-contrast
// inversion), inactive tabs use neutral borders. No brand gradients.
const PLATFORMS: { value: DownloadPlatform; label: string; icon: typeof Instagram; hint: string }[] = [
  { value: "instagram", label: "Instagram", icon: Instagram, hint: "Posts · Stories · Highlights" },
  { value: "twitter", label: "Twitter / X", icon: Twitter, hint: "Tweets · Videos · Spaces" },
  { value: "tiktok", label: "TikTok", icon: Music2, hint: "Videos · User feed" },
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
  // Paste reel IDs here when IG's /user/highlights/ GraphQL gate blocks you
  // — each ID is the 19-digit suffix in /stories/highlights/<id> URLs.
  const [highlightIds, setHighlightIds] = useState("");
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
  });

  const fromHighlightIdsMut = useMutation({
    mutationFn: async (payload: { user: string; ids: string[] }) =>
      (await api.post("/api/downloads/from-highlight-ids", payload)).data,
    onSuccess: (res) => {
      toast.success(`Queued ${res.created} highlight reel${res.created === 1 ? "" : "s"}${res.skipped ? ` (skipped ${res.skipped})` : ""}`);
      setHighlightIds("");
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["downloads-stats"] });
      qc.invalidateQueries({ queryKey: ["pending-summary-all"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed to queue highlight IDs"),
  });

  function parseLinks(): { url: string; author?: string }[] {
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
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-lg flex items-center gap-2">
            <Plus className="h-5 w-5" /> Add to download queue
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
        {/* ----- Pill row: platform (layer 1) + source (layer 2) in one line (plan §6.1) ----- */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div role="radiogroup" aria-label="Nền tảng" className="flex flex-wrap items-center gap-1.5">
            {PLATFORMS.map((p) => {
              const active = platform === p.value;
              return (
                <button
                  key={p.value}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setPlatform(p.value)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "border-accent bg-accent-soft text-ink"
                      : "border-border text-ink-2 hover:bg-surface-2 hover:text-ink"
                  )}
                >
                  <PlatformDot platform={p.value} />
                  {p.label}
                </button>
              );
            })}
          </div>
          <div className="hidden h-5 w-px bg-border md:block" />
          <div role="radiogroup" aria-label="Nguồn" className="flex flex-wrap items-center gap-1.5">
            {SOURCES.filter((s) => s.value !== "database" || platform !== "tiktok").map((s) => {
              const Icon = s.icon;
              const active = source === s.value;
              return (
                <button
                  key={s.value}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setSource(s.value)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "border-accent bg-accent-soft text-ink"
                      : "border-border text-ink-2 hover:bg-surface-2 hover:text-ink"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {s.label}
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
                { key: "posts", label: "Posts", desc: "Timeline feed", value: layerPosts, set: setLayerPosts },
                { key: "stories", label: "Stories", desc: "24h expiring", value: layerStories, set: setLayerStories },
                { key: "highlights", label: "Highlights", desc: "Permanent reels", value: layerHighlights, set: setLayerHighlights },
              ].map((opt) => {
                const active = opt.value;
                return (
                  <button
                    key={opt.key}
                    onClick={() => opt.set(!opt.value)}
                    className={cn(
                      "flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card hover:border-foreground/30"
                    )}
                  >
                    <div className="flex items-center gap-2 w-full">
                      <div className={cn(
                        "flex h-4 w-4 items-center justify-center rounded border transition-colors",
                        active
                          ? "border-primary-foreground bg-primary-foreground text-primary"
                          : "border-border bg-card"
                      )}>
                        {active && <CheckCircle2 className="h-3 w-3" />}
                      </div>
                      <div className={cn("text-sm font-medium", active && "text-primary-foreground")}>{opt.label}</div>
                    </div>
                    <div className={cn(
                      "text-[10px] pl-6",
                      active ? "text-primary-foreground/70" : "text-muted-foreground"
                    )}>{opt.desc}</div>
                  </button>
                );
              })}
            </div>
            <div className="text-[10px] text-muted-foreground mt-1.5">
              Tip: split into separate runs to avoid IG rate-limits
            </div>
            {layerHighlights && (
              <div className="mt-3 rounded-lg border border-border bg-card p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="text-xs font-semibold">Bulk highlight IDs (workaround)</div>
                </div>
                <div className="text-[10px] text-muted-foreground leading-relaxed">
                  Instagram blocks <code>/user/highlights/</code> for non-browser
                  requests. Paste the username + reel IDs (the 19-digit number in each
                  <code className="mx-1">/stories/highlights/&lt;id&gt;</code> URL from your browser) instead.
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <Input
                    placeholder="username (e.g. hienthuc.27)"
                    value={(() => {
                      const m = text.match(/instagram\.com\/([\w.]+)/);
                      return m ? m[1] : "";
                    })()}
                    onChange={(e) => setText(`https://www.instagram.com/${e.target.value.replace(/^@/, "")}/\n${text}`)}
                    className="bg-background text-xs"
                  />
                  <textarea
                    placeholder={"One reel ID per line, e.g.\n17855571861642291\n17841549891124450"}
                    value={highlightIds}
                    onChange={(e) => setHighlightIds(e.target.value)}
                    rows={3}
                    className="md:col-span-2 w-full rounded-md border border-border bg-background px-3 py-2 text-xs font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[10px] text-muted-foreground">
                    {highlightIds.split(/\r?\n/).map((s) => s.trim()).filter((s) => /^\d{15,22}$/.test(s)).length} valid ID(s) detected
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const userMatch = text.match(/instagram\.com\/([\w.]+)/);
                      const user = userMatch ? userMatch[1] : "";
                      if (!user) { toast.error("Type the username first"); return; }
                      const ids = highlightIds
                        .split(/[\s,]+/)
                        .map((s) => s.trim())
                        .filter((s) => /^\d{15,22}$/.test(s));
                      if (ids.length === 0) { toast.error("Paste at least one valid ID"); return; }
                      fromHighlightIdsMut.mutate({ user, ids });
                    }}
                    disabled={fromHighlightIdsMut.isPending}
                    className="gap-1.5"
                  >
                    {fromHighlightIdsMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                    Queue highlight IDs
                  </Button>
                </div>
              </div>
            )}
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
          <div className="rounded-lg border border-border bg-background p-3 max-h-64 overflow-y-auto space-y-1">
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
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted cursor-pointer"
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
                    <div className="h-6 w-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold border border-border">
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
          className="w-full bg-primary text-primary-foreground hover:bg-primary/90 font-semibold"
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
  let targets: string[] = [];
  try { targets = job?.targets ? JSON.parse(job.targets) : []; } catch { targets = []; }

  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-wrap items-center gap-3 p-3">
        <div className="mr-auto flex min-w-48 items-center gap-2">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", job ? "animate-pulse bg-info" : "bg-muted-foreground")} />
          <div className="min-w-0">
            {job ? (
              <div className="text-xs font-medium">
                Job <span className="font-mono text-accent">#{job.id}</span>
                <span className="ml-2 font-mono text-muted-foreground">{formatDuration(elapsed)} · {job.new_files_count} files</span>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                {totalResumable ? `${totalResumable} mục sẵn sàng tiếp tục` : "Không có job đang chạy"}
              </div>
            )}
          </div>
          {job && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => stopMut.mutate(job.id)}
              disabled={stopMut.isPending}
              className="h-7 gap-1.5 px-2 text-xs"
            >
              {stopMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />}
              Stop
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ResumeAction platform="instagram" label="IG" summary={ig} running={targets.some((target) => target.includes("instagram.com"))} pending={runMut.isPending && runMut.variables === "instagram"} onClick={() => runMut.mutate("instagram")} />
          <ResumeAction platform="twitter" label="X" summary={tw} running={targets.some((target) => target.includes("x.com") || target.includes("twitter.com"))} pending={runMut.isPending && runMut.variables === "twitter"} onClick={() => runMut.mutate("twitter")} />
          <ResumeAction platform="tiktok" label="TikTok" summary={tt} running={targets.some((target) => target.includes("tiktok.com"))} pending={runMut.isPending && runMut.variables === "tiktok"} onClick={() => runMut.mutate("tiktok")} />
        </div>
      </CardContent>
    </Card>
  );
}

function ResumeAction({ platform, label, summary, running, pending, onClick }: {
  platform: DownloadPlatform;
  label: string;
  summary: PendingSummary | undefined;
  running: boolean;
  pending: boolean;
  onClick: () => void;
}) {
  const count = summary?.resumable ?? 0;
  return (
    <Button
      size="sm"
      variant={count ? "default" : "outline"}
      disabled={running || pending || count === 0}
      onClick={onClick}
      className="h-7 gap-1.5 px-2 text-xs"
      aria-label={`Tiếp tục ${label}: ${count} mục`}
    >
      {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
      {label}<span className="font-mono opacity-70">{count}</span>
    </Button>
  );
}

function ResumeRow({
  platform, label, icon: Icon, summary, running, isPending, onResume,
}: {
  platform: DownloadPlatform;
  label: string;
  icon: typeof Instagram;
  summary: PendingSummary | undefined;
  running: boolean;
  isPending: boolean;
  onResume: () => void;
}) {
  const resumable = summary?.resumable ?? 0;
  const disabled = running || resumable === 0 || isPending;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-muted">
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium flex items-center gap-2">
          {label}
          {running && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider status-success flex items-center gap-1">
              <Loader2 className="h-2.5 w-2.5 animate-spin" /> running
            </span>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-2 flex-wrap">
          <span><span className="text-warning">{summary?.pending ?? 0}</span> pending</span>
          <span className="text-muted-foreground/50">·</span>
          <span>{summary?.in_flight ?? 0} in_flight</span>
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
          resumable > 0 && !running && "bg-primary text-primary-foreground hover:bg-primary/90"
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

  const platEntries: [DownloadPlatform, number][] = (Object.keys(PLATFORM_LABELS) as DownloadPlatform[])
    .map((platform) => [platform, stats.by_platform[platform] ?? 0]);
  const statusEntries = Object.entries(stats.by_status);

  return (
    <div className="flex h-full flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <TrendingUp className="h-4 w-4" /> Queue theo nền tảng
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {platEntries.map(([p, n]) => (
                <PlatformBar
                  key={p}
                  platform={p as DownloadPlatform}
                  count={n}
                  max={Math.max(...platEntries.map(([_, v]) => v), 1)}
                />
              ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4" /> Trạng thái hàng đợi
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {statusEntries.length === 0
              ? <div className="col-span-full text-xs text-muted-foreground">Chưa có download</div>
              : statusEntries.map(([s, n]) => <StatusPill key={s} status={s} count={n} />)}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3 text-center">
            <div><div className="text-lg font-semibold">{stats.last_24h}</div><div className="text-[10px] text-muted-foreground">24 giờ</div></div>
            <div><div className="text-lg font-semibold">{stats.last_7d}</div><div className="text-[10px] text-muted-foreground">7 ngày</div></div>
            <div><div className="text-lg font-semibold">{formatBytes(stats.total_size_bytes)}</div><div className="text-[10px] text-muted-foreground">Dung lượng</div></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PlatformBar({ platform, count, max }: { platform: DownloadPlatform; count: number; max: number }) {
  const cfg = PLATFORMS.find((p) => p.value === platform)!;
  const pct = Math.round((count / max) * 100);
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <PlatformDot platform={platform} />
          <span className="text-sm font-medium">{cfg.label}</span>
        </div>
        <span className="text-xs font-mono text-muted-foreground">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const PLATFORM_LABELS: Record<DownloadPlatform, string> = {
  instagram: "Instagram",
  twitter: "Twitter / X",
  tiktok: "TikTok",
};

// Status colors: success / error / info carry brand color; pending & skipped
// are neutral so only meaningful state stands out.
const STATUS_META: Record<string, { icon: typeof Clock; cls: string; label: string }> = {
  pending:     { icon: Clock,      cls: "border border-border bg-card text-foreground",       label: "Pending" },
  downloading: { icon: Loader2,    cls: "status-info",                                         label: "Downloading" },
  completed:   { icon: CheckCircle2, cls: "status-success",                                    label: "Completed" },
  failed:      { icon: XCircle,    cls: "status-error",                                        label: "Failed" },
  skipped:     { icon: XCircle,    cls: "status-muted",                                        label: "Skipped" },
};

function StatusPill({ status, count }: { status: string; count: number }) {
  const meta = STATUS_META[status] || { icon: Clock, cls: "status-muted", label: status };
  const Icon = meta.icon;
  return (
    <div className={cn("flex items-center gap-2 rounded-lg px-3 py-2", meta.cls)}>
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

function classifyLogLine(line: string): { tone: "info" | "success" | "warn" | "error" | "muted"; tag?: { kind: string; cls: string; label: string } } {
  const l = line.toLowerCase();
  if (!line.trim()) return { tone: "muted" };
  // Detect platform + content_type tag from "Download #N [platform/ct]" lines.
  // Backend prefixes user_start/user_done with "→ @user" / "done @user".
  const tagMatch = line.match(/\[(\w+)\/(\w+)]/);
  let tag: { kind: string; cls: string; label: string } | undefined;
  if (tagMatch) {
    const [, plat, ct] = tagMatch;
    const k = `${plat}/${ct}`;
    tag = { kind: k, cls: TAG_CLS[k] ?? "border border-border bg-muted text-foreground", label: k };
  }
  if (l.includes("[error]") || l.includes("error:") || l.includes("exception") || l.includes("failed") || l.includes("exit code")) {
    return { tone: "error", tag };
  }
  if (l.includes("warn") || l.includes("rate limit") || l.includes("429") || l.includes("rate-limit")) {
    return { tone: "warn", tag };
  }
  if (l.includes("done ") || l.includes("completed") || l.includes("media:") || l.includes("new=") || l.includes("user_done")) {
    return { tone: "success", tag };
  }
  if (l.startsWith("-->") || l.startsWith("done") || l.includes("downloading") || l.includes("launching")) {
    return { tone: "info", tag };
  }
  return { tone: "muted", tag };
}

// Per-tag pill colors. Now using only neutral surfaces — borders + lowercase
// background tint for visual grouping. Status colors stay for error/warn.
const TAG_CLS: Record<string, string> = {
  "instagram/post":      "border border-border bg-muted text-foreground",
  "instagram/story":     "border border-border bg-muted text-foreground",
  "instagram/highlight": "border border-border bg-muted text-foreground",
  "twitter/tweet":       "border border-border bg-muted text-foreground",
  "twitter/live":        "border border-border bg-muted text-foreground",
  "tiktok/tiktok":       "border border-border bg-muted text-foreground",
};

// Tone palette: only success/warn/error carry color; info/muted are neutral.
const TONE_CLS: Record<string, { text: string; gutter: string; prefix: string }> = {
  info:    { text: "text-foreground/80", gutter: "text-muted-foreground/40", prefix: "›" },
  success: { text: "text-success",       gutter: "text-success/40",          prefix: "✓" },
  warn:    { text: "text-warning",       gutter: "text-warning/40",          prefix: "!" },
  error:   { text: "text-destructive",  gutter: "text-destructive/40",      prefix: "×" },
  muted:   { text: "text-muted-foreground", gutter: "text-muted-foreground/30", prefix: "·" },
};

function LiveTerminal() {
  const containerRef = useRef<HTMLDivElement>(null);
  const linesRef = useRef<{ ts: number; text: string }[]>([]);
  const [lineCount, setLineCount] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState<"all" | "info" | "success" | "warn" | "error" | "post" | "story" | "highlight" | "tweet" | "tiktok">("all");
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

  // Filter view (does not mutate the underlying buffer). When the filter is
  // a content-type token we also check the tag.kind suffix.
  const visible = (filter === "all"
    ? linesRef.current
    : linesRef.current.filter((l) => {
        const { tone, tag } = classifyLogLine(l.text);
        if (tone === filter) return true;
        if (tag && tag.kind.endsWith(`/${filter}`)) return true;
        return false;
      })
  ).slice(-MAX_LINES);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-3 flex-wrap pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted">
            <Terminal className="h-4 w-4" />
          </div>
          <CardTitle className="text-base flex items-center gap-2">
            Live terminal
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider border",
              connected === "live" && "status-success",
              connected === "polling" && "border border-warning/30 text-warning",
              connected === "connecting" && "status-muted",
              connected === "offline" && "status-error"
            )}>
              {connected === "live" && "● live"}
              {connected === "polling" && "◐ polling"}
              {connected === "connecting" && "○ connecting"}
              {connected === "offline" && "○ offline"}
            </span>
          </CardTitle>
          {job ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground ml-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Job <span className="font-mono">#{job.id}</span></span>
              <span>·</span>
              <span className="font-mono">{job.new_files_count} new</span>
              <span>·</span>
              <span className="font-mono">{formatDuration(elapsed)}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground ml-2">
              <span className="h-2 w-2 rounded-full bg-muted" />
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
                "px-2 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors border",
                filter === f
                  ? "border-primary bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground border-transparent"
              )}
            >
              {f}
            </button>
          ))}
          <div className="w-px h-5 bg-border mx-1" />
          {([
            { v: "post",      cls: "border border-primary bg-primary text-primary-foreground" },
            { v: "story",     cls: "border border-primary bg-primary text-primary-foreground" },
            { v: "highlight", cls: "border border-primary bg-primary text-primary-foreground" },
            { v: "tweet",     cls: "border border-primary bg-primary text-primary-foreground" },
            { v: "tiktok",    cls: "border border-primary bg-primary text-primary-foreground" },
          ] as const).map((f) => (
            <button
              key={f.v}
              onClick={() => setFilter(f.v as any)}
              className={cn(
                "px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider transition-colors",
                filter === f.v
                  ? f.cls
                  : "border border-border text-muted-foreground hover:text-foreground"
              )}
              title={`Filter ${f.v} events`}
            >
              {f.v}
            </button>
          ))}
          <div className="w-px h-5 bg-border mx-1" />
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
        <div className="relative">
          <div className="px-3 py-1.5 text-[10px] text-muted-foreground border-y border-border bg-card flex items-center justify-between">
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
            className="h-[360px] overflow-y-auto bg-background px-3 py-2 font-mono text-[11px] leading-5 border-t border-border"
          >
            {visible.length === 0 ? (
              <div className="text-muted-foreground italic px-1 py-2">
                {lineCount === 0
                  ? "▌ no events yet — start a job above to see live output"
                  : "▌ no lines match the current filter"}
              </div>
            ) : (
              visible.map((l, i) => {
                const { tone, tag } = classifyLogLine(l.text);
                const t = TONE_CLS[tone] ?? TONE_CLS.muted;
                return (
                  <div
                    key={i}
                    className="group flex gap-3 items-baseline -mx-3 px-3 py-0.5 hover:bg-muted/50 transition-colors"
                  >
                    {/* Line number gutter — fades so it doesn't fight the content */}
                    <span className="text-muted-foreground/40 select-none w-8 flex-shrink-0 text-right tabular-nums">
                      {String(visible.length - i).padStart(3, " ")}
                    </span>
                    {/* Timestamp */}
                    <span className={cn("select-none w-16 flex-shrink-0 tabular-nums", t.gutter)}>
                      {new Date(l.ts).toLocaleTimeString("en-GB", { hour12: false })}
                    </span>
                    {/* Tone prefix icon */}
                    <span className={cn("select-none w-3 flex-shrink-0 text-center", t.text)}>
                      {t.prefix}
                    </span>
                    {/* Optional platform/content_type tag — only on the first line of a job */}
                    {tag && (
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider flex-shrink-0",
                        tag.cls,
                      )}>
                        {tag.label}
                      </span>
                    )}
                    <span className={cn("whitespace-pre-wrap break-all", t.text)}>
                      {l.text}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
