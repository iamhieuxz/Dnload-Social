"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DownloadPlatform, type DownloadSource, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { PlatformDot } from "@/components/PlatformDot";
import { ShortcutChip } from "@/components/ShortcutChip";
import { StatusDeck } from "@/components/StatusDeck";
import { ControlRail } from "@/components/ControlRail";
import { TopAccounts } from "@/components/TopAccounts";
import { useSystemWebSocket, type LogEvent } from "@/lib/websocket";
import {
  Instagram, Twitter, Link2, ListTree, Database, Loader2,
  Plus, CheckCircle2, Download as DownloadIcon,
  Terminal, Trash2, Pause, Play, Square, Music2,
} from "lucide-react";
import { toast } from "sonner";
import { cn, formatBytes, formatDuration, formatNumber } from "@/lib/utils";

export default function DashboardPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Instagram và X tải song song, nhịp độ tự giãn theo tín hiệu rate limit"
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
      <StatusDeck />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-7 xl:col-span-8">
          <DownloadConsole />
        </div>
        <aside className="space-y-5 lg:col-span-5 xl:col-span-4">
          <ControlRail />
          <TopAccounts />
        </aside>
      </div>
      <LiveTerminal />
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
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 tab-type transition-colors",
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
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 tab-type transition-colors",
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
            <div className="mt-1.5 text-[10px] text-muted-foreground">
              Nhịp giữa các account do app tự giãn (18–45s, cooldown khi bị throttle) — không cần chia nhỏ run.
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
                    id="ig-username"
                    name="ig-username"
                    aria-label="Tên tài khoản Instagram"
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
              id="download-url"
              name="download-url"
              aria-label="URL cần tải"
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
// Live terminal — one stream, colour-coded by platform
// =========================================================================

const MAX_LINES = 500;

type TermLine = {
  ts: number;
  text: string;
  /** Which download stream produced the line; set by the backend's log
   *  handler from the job's platform, so it never has to be guessed from
   *  the filename (Instagram and X both write plain "[NEW] <file>" lines). */
  platform?: string;
};

const PLATFORM_UI: Record<
  string,
  { short: string; label: string; chip: string; dot: string }
> = {
  instagram: {
    short: "IG",
    label: "Instagram",
    chip: "border-plat-ig/30 bg-plat-ig/10 text-plat-ig",
    dot: "bg-plat-ig",
  },
  twitter: {
    short: "X",
    label: "X / Twitter",
    chip: "border-plat-x/30 bg-plat-x/10 text-plat-x",
    dot: "bg-plat-x",
  },
  tiktok: {
    short: "TT",
    label: "TikTok",
    chip: "border-plat-tiktok/30 bg-plat-tiktok/10 text-plat-tiktok",
    dot: "bg-plat-tiktok",
  },
};

/** Tone comes from the backend's tag prefix — no guessing at message bodies. */
function levelOf(text: string): "info" | "success" | "warn" | "error" | "muted" {
  if (text.startsWith("[ERR]")) return "error";
  if (text.startsWith("[RATE]")) return "warn";
  if (text.startsWith("[OK]")) return "success";
  if (text.startsWith("[SKIP]")) return "muted";
  if (text.startsWith("JOB ")) return "success";
  if (text.startsWith("[NEW]")) return "info";
  return "muted";
}

const TONE_TEXT: Record<string, string> = {
  info: "text-ink-2",
  success: "text-success",
  warn: "text-warning",
  error: "text-destructive",
  muted: "text-ink-3",
};

type LevelFilter = "all" | "error" | "warn";

function LiveTerminal() {
  const containerRef = useRef<HTMLDivElement>(null);
  const linesRef = useRef<TermLine[]>([]);
  // The same event reaches us twice: once over the WebSocket and once from
  // the polling fallback that always runs alongside it. Server timestamps
  // are identical on both copies, so they are the dedupe key.
  const seenRef = useRef<Set<string>>(new Set());
  const [lineCount, setLineCount] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [level, setLevel] = useState<LevelFilter>("all");
  const [platformFilter, setPlatformFilter] = useState<string>("all");
  const qc = useQueryClient();
  // Data-driven chrome is gated on mount so the first client render matches
  // the server-rendered HTML (the queries below resolve before hydration
  // finishes on a slow first paint).
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  // Same cache entry as ControlRail — one request for both panels.
  const { data: jobsData } = useQuery<{ items: Job[] }>({
    queryKey: ["jobs", "running"],
    queryFn: async () =>
      (await api.get("/api/jobs", { params: { status: "running", page_size: 10 } })).data,
    refetchInterval: 3_000,
  });
  const running = mounted ? jobsData?.items ?? [] : [];

  const { connected, resetCursor } = useSystemWebSocket((event: LogEvent) => {
    if (event.type === "log") {
      const text: string = event.data?.message ?? "";
      if (!text) return;
      const serverTs: number | null =
        typeof event.data?.ts === "number" ? event.data.ts : null;
      push(
        {
          ts: serverTs ? serverTs * 1000 : Date.now(),
          text,
          platform: event.data?.platform ?? undefined,
        },
        serverTs ? `${serverTs}|${text}` : undefined
      );
    } else if (event.type === "job_update" || event.type === "status") {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      const id = event.data?.job_id;
      const status = event.data?.status;
      if (id && status) {
        const platform = event.data?.platform;
        const newFiles = event.data?.new_files;
        push({
          ts: Date.now(),
          platform: platform ?? undefined,
          text:
            newFiles != null
              ? `JOB #${id} ${String(status).toUpperCase()} · ${newFiles} file · ${event.data?.processed ?? 0} account`
              : `JOB #${id} ${String(status).toUpperCase()}`,
        });
      }
    }
  });

  function push(line: TermLine, dedupeKey?: string) {
    if (dedupeKey) {
      if (seenRef.current.has(dedupeKey)) return;
      seenRef.current.add(dedupeKey);
      if (seenRef.current.size > 2000) seenRef.current.clear();
    }
    linesRef.current.push(line);
    if (linesRef.current.length > MAX_LINES) {
      linesRef.current = linesRef.current.slice(-MAX_LINES);
    }
    setLineCount(linesRef.current.length);
    scrollToBottom();
  }

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
    setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 30);
  }

  function clear() {
    linesRef.current = [];
    seenRef.current.clear();
    setLineCount(0);
    resetCursor();
  }

  // Per-platform counters for the filter chips (also the at-a-glance answer to
  // "which stream is doing what right now").
  const counts: Record<string, number> = { instagram: 0, twitter: 0, tiktok: 0 };
  for (const line of linesRef.current) {
    if (line.platform && counts[line.platform] !== undefined) counts[line.platform] += 1;
  }

  const visible = linesRef.current.filter((l) => {
    if (platformFilter !== "all" && l.platform !== platformFilter) return false;
    if (level === "all") return true;
    const tone = levelOf(l.text);
    if (level === "error") return tone === "error";
    return tone === "warn" || tone === "error";
  });

  const errorCount = linesRef.current.filter((l) => levelOf(l.text) === "error").length;
  const warnCount = linesRef.current.filter((l) => levelOf(l.text) === "warn").length;

  const levelChips: { key: LevelFilter; label: string; count?: number }[] = [
    { key: "all", label: "Tất cả" },
    { key: "error", label: "Lỗi", count: errorCount },
    { key: "warn", label: "Cảnh báo", count: warnCount },
  ];

  return (
    <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-white/[0.06] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden="true" />
          <h2 className="text-[13px] font-medium">Nhật ký trực tiếp</h2>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider",
              connected === "live" && "border-success/30 text-success",
              connected === "polling" && "border-warning/30 text-warning",
              connected === "connecting" && "border-white/[0.08] text-ink-3",
              connected === "offline" && "border-destructive/30 text-destructive"
            )}
          >
            <span
              className={cn(
                "h-1 w-1 rounded-full",
                connected === "live" ? "bg-success" : connected === "polling" ? "bg-warning" : "bg-ink-3"
              )}
            />
            {connected === "live" ? "live" : connected === "polling" ? "polling" : connected}
          </span>
          <span className="truncate font-mono text-[10px] text-ink-3">
            {mounted && running.length > 0
              ? `${running.length} luồng · ${formatNumber(
                  running.reduce((sum, j) => sum + (j.new_files_count ?? 0), 0)
                )} file`
              : "không có job"}
            {" · "}
            {formatNumber(lineCount)} dòng
          </span>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {levelChips.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => setLevel(c.key)}
              aria-pressed={level === c.key}
              className={cn(
                "rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
                level === c.key
                  ? "border-white/20 bg-white/[0.08] text-ink"
                  : "border-transparent text-ink-3 hover:text-ink-2"
              )}
            >
              {c.label}
              {c.count ? <span className="ml-1 opacity-70">{c.count}</span> : null}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-white/[0.08]" />
          <button
            type="button"
            onClick={() => setPlatformFilter("all")}
            aria-pressed={platformFilter === "all"}
            className={cn(
              "rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
              platformFilter === "all"
                ? "border-white/20 bg-white/[0.08] text-ink"
                : "border-transparent text-ink-3 hover:text-ink-2"
            )}
          >
            mọi nền tảng
          </button>
          {(["instagram", "twitter", "tiktok"] as const).map((p) => {
            const ui = PLATFORM_UI[p];
            const n = counts[p] ?? 0;
            return (
              <button
                key={p}
                type="button"
                onClick={() => setPlatformFilter(platformFilter === p ? "all" : p)}
                title={ui.label}
                aria-pressed={platformFilter === p}
                className={cn(
                  "inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-[10px] tracking-wider transition-colors",
                  platformFilter === p
                    ? ui.chip
                    : "border-transparent text-ink-3 hover:text-ink-2"
                )}
              >
                <span className={cn("h-1.5 w-1.5 rounded-full", ui.dot, n === 0 && "opacity-30")} />
                {ui.short}
                <span className="tabular-nums opacity-70">{formatNumber(n)}</span>
              </button>
            );
          })}
          <span className="mx-1 h-4 w-px bg-white/[0.08]" />
          <button
            type="button"
            onClick={() => setAutoScroll((v) => !v)}
            title={autoScroll ? "Tạm dừng cuộn tự động" : "Cuộn tự động"}
            className="rounded p-1 text-ink-3 transition-colors hover:text-ink"
          >
            {autoScroll ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={clear}
            title="Xoá buffer"
            className="rounded p-1 text-ink-3 transition-colors hover:text-ink"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </header>

      <div className="relative">
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-[380px] overflow-y-auto bg-[#08080B] py-1.5 font-mono text-[11px] leading-[1.6]"
        >
          {visible.length === 0 ? (
            <div className="px-4 py-3 text-ink-3">
              {lineCount === 0
                ? "▌ chưa có sự kiện — chạy một job ở console phía trên"
                : "▌ không có dòng nào khớp bộ lọc"}
            </div>
          ) : (
            visible.map((l, i) => {
              const tone = levelOf(l.text);
              const ui = l.platform ? PLATFORM_UI[l.platform] : undefined;
              return (
                <div
                  key={`${l.ts}-${i}`}
                  className="grid grid-cols-[2.25rem_4.25rem_2rem_minmax(0,1fr)] items-baseline gap-2 px-3 py-[1px] hover:bg-white/[0.03]"
                >
                  <span className="select-none text-right tabular-nums text-white/15">
                    {String(i + 1).padStart(3, " ")}
                  </span>
                  <span className="select-none tabular-nums text-ink-3/70">
                    {new Date(l.ts).toLocaleTimeString("en-GB", { hour12: false })}
                  </span>
                  {ui ? (
                    <span
                      className={cn(
                        "inline-flex h-[15px] items-center justify-center rounded border text-[9px] font-semibold tracking-wider",
                        ui.chip
                      )}
                      title={ui.label}
                    >
                      {ui.short}
                    </span>
                  ) : (
                    <span className="text-white/10 select-none">·</span>
                  )}
                  <span className={cn("whitespace-pre-wrap break-all", TONE_TEXT[tone])}>
                    {l.text}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {!autoScroll && (
          <button
            type="button"
            onClick={() => {
              setAutoScroll(true);
              scrollToBottom();
            }}
            className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-accent backdrop-blur transition-colors hover:bg-accent/15"
          >
            <Square className="h-2.5 w-2.5 fill-accent" /> xuống cuối
          </button>
        )}
      </div>
    </section>
  );
}
