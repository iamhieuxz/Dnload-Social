"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type DashboardStatsFE, type PlatformCountFE } from "@/lib/api";
import { cn, formatBytes, formatNumber } from "@/lib/utils";
import {
  Users, Image, HardDrive, Activity, Clock, Download as DownloadIcon,
  Instagram, Twitter, Music2, AlertTriangle, Film, CheckCircle2,
  XCircle, Pause, ShieldAlert, Server, ListChecks, Star, Database,
} from "lucide-react";

const PLATFORM_META: Record<string, { label: string; icon: typeof Users; gradient: string; short: string }> = {
  instagram: { label: "Instagram", icon: Instagram, gradient: "bg-muted", short: "IG" },
  twitter:   { label: "Twitter / X", icon: Twitter, gradient: "bg-muted", short: "X" },
  tiktok:    { label: "TikTok",     icon: Music2, gradient: "bg-muted", short: "TT" },
};

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.min(100, (part / total) * 100);
}

function pctOf(a: number, b: number): number {
  return b > 0 ? Math.min(100, (a / b) * 100) : 0;
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function StatCards() {
  const dash = useQuery<DashboardStatsFE>({
    queryKey: ["stats-dashboard"],
    queryFn: async () => (await api.get("/api/stats/dashboard")).data,
    refetchInterval: 5_000,
  });

  if (dash.isLoading || !dash.data) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} >
              <CardContent className="p-5 space-y-3">
                <div className="h-4 w-24 shimmer rounded" />
                <div className="h-8 w-16 shimmer rounded" />
                <div className="h-3 w-32 shimmer rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <Card key={i} >
              <CardContent className="p-5 space-y-3">
                <div className="h-4 w-32 shimmer rounded" />
                <div className="h-12 w-full shimmer rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const s = dash.data;
  const usedPct = s.disk_total_bytes
    ? pct(s.disk_used_bytes, s.disk_total_bytes)
    : 0;
  const totalActive = s.pending_count + s.in_flight_count;
  const rateLimitTone = s.rate_limit_events_24h === 0
    ? "success"
    : s.rate_limit_events_24h > 5
      ? "destructive"
      : "warning";

  return (
    <div className="space-y-4">
      {/* ----- Row 1: 4 hero stats ----- */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <HeroStat
          idx={0}
          icon={Users}
          title="Accounts"
          value={formatNumber(s.total_accounts)}
          sub={`${formatNumber(s.total_media)} media indexed in DB`}
          tone="primary"
        />
        <HeroStat
          idx={1}
          icon={Image}
          title="Media trên đĩa"
          value={formatNumber(s.files_on_disk)}
          sub={`${formatNumber(s.folders_on_disk)} folders · ${formatBytes(s.disk_used_bytes)} trong folder download`}
          tone="accent"
        />
        <HeroStat
          idx={2}
          icon={ListChecks}
          title="Queue"
          value={formatNumber(totalActive)}
          sub={`${s.pending_count} pending · ${s.in_flight_count} đang chạy`}
          tone={totalActive > 50 ? "warning" : "muted"}
        />
        <HeroStat
          idx={3}
          icon={Activity}
          title="Jobs · 24h"
          value={`${s.jobs_completed_24h} ✓`}
          sub={`${s.jobs_failed_24h} ✗ · ${s.jobs_stopped_24h} ⏸ · ${s.jobs_running} running`}
          tone={s.jobs_failed_24h > s.jobs_completed_24h ? "destructive" : "success"}
        />
      </div>

      {/* ----- Row 2: Disk + Per-platform ----- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* --- Disk usage --- */}
        <Card  className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-warning" /> Tổng dung lượng ổ đĩa
              {s.disk_total_bytes > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground font-mono">
                  {formatBytes(s.disk_used_bytes)} / {formatBytes(s.disk_total_bytes)}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {s.disk_total_bytes === 0 ? (
              <div className="text-xs text-muted-foreground py-4">
                Không đọc được disk usage (volume không hỗ trợ statfs).
              </div>
            ) : (
              <>
                <div>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                    <span>Used</span>
                    <span className="font-mono">{usedPct.toFixed(1)}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn(
                        "h-full transition-all",
                        usedPct > 90
                          ? "bg-destructive"
                          : usedPct > 75
                            ? "bg-warning"
                            : "bg-primary"
                      )}
                      style={{ width: `${usedPct}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-lg font-bold">{formatBytes(s.disk_used_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Used</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-success">{formatBytes(s.disk_free_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Free</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold">{formatBytes(s.disk_total_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Total</div>
                  </div>
                </div>
                {usedPct > 90 && (
                  <div className="flex items-center gap-2 rounded-md bg-destructive/10 border border-destructive/30 px-2.5 py-1.5 text-[11px] text-destructive">
                    <AlertTriangle className="h-3 w-3" />
                    <span>Ổ đĩa sắp đầy — dọn file cũ hoặc đổi <span className="font-mono">download_folder</span> trong <span className="font-mono">.env</span>.</span>
                  </div>
                )}
              </>
            )}
            <div className="pt-3 border-t border-border grid grid-cols-2 gap-3 text-center">
              <div>
                <div className="text-sm font-bold">{formatNumber(s.files_on_disk)}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Files on disk</div>
              </div>
              <div>
                <div className="text-sm font-bold">{formatBytes(s.total_size_bytes)}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Trong download folders</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* --- Per-platform breakdown --- */}
        <Card  className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Server className="h-4 w-4 text-primary" /> Theo nền tảng
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {s.by_platform.map((p) => (
                <PlatformRow key={p.platform} p={p} />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ----- Row 3: Media by type + Top accounts ----- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card  className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Film className="h-4 w-4 text-accent" /> Media theo loại (DB)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <MediaTypeRow
              label="Posts"
              count={s.media_by_type.posts}
              max={Math.max(
                s.media_by_type.posts,
                s.media_by_type.stories,
                s.media_by_type.highlights,
                1,
              )}
              gradient="bg-muted"
            />
            <MediaTypeRow
              label="Stories"
              count={s.media_by_type.stories}
              max={Math.max(
                s.media_by_type.posts,
                s.media_by_type.stories,
                s.media_by_type.highlights,
                1,
              )}
              gradient="bg-muted"
            />
            <MediaTypeRow
              label="Highlights"
              count={s.media_by_type.highlights}
              max={Math.max(
                s.media_by_type.posts,
                s.media_by_type.stories,
                s.media_by_type.highlights,
                1,
              )}
              gradient="bg-muted"
            />
            <div className="pt-3 border-t border-border grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-lg font-bold">{formatNumber(s.downloads_24h)}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Last 24h</div>
              </div>
              <div>
                <div className="text-lg font-bold">{formatNumber(s.downloads_7d)}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Last 7d</div>
              </div>
              <div>
                <div className="text-xs font-bold">{relativeTime(s.last_download_at)}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Mới nhất</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card  className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Star className="h-4 w-4 text-warning" /> Top accounts (theo dung lượng)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {s.top_accounts_by_size.length === 0 ? (
              <div className="text-xs text-muted-foreground py-6 text-center space-y-1">
                <Database className="h-6 w-6 mx-auto opacity-40" />
                <div>Chưa scan account nào. Vào tab <span className="font-mono">Accounts</span> để index thư mục download.</div>
              </div>
            ) : (
              <div className="space-y-2">
                {s.top_accounts_by_size.map((a, i) => (
                  <div
                    key={a.id}
                    className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-[10px] font-bold">
                      #{i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate flex items-center gap-1.5">
                        @{a.username}
                        {a.is_dead && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">dead</span>
                        )}
                      </div>
                      <div className="text-[10px] text-muted-foreground font-mono">
                        {formatNumber(a.total_posts)} posts · {formatNumber(a.total_stories)} stories · {formatNumber(a.total_highlights)} highlights
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold">{formatBytes(a.total_size_bytes)}</div>
                      <div className="text-[10px] text-muted-foreground">{relativeTime(a.last_scanned_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ----- Row 4: System health strip ----- */}
      <Card  className="overflow-hidden">
        <CardContent className="p-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SystemHealth
              icon={CheckCircle2}
              tone="success"
              title="Success rate · 24h"
              value={s.success_rate_24h < 0 ? "—" : `${(s.success_rate_24h * 100).toFixed(0)}%`}
              sub={`${s.jobs_completed_24h} ok / ${s.jobs_failed_24h} fail`}
            />
            <SystemHealth
              icon={Pause}
              tone="muted"
              title="Jobs stopped · 24h"
              value={formatNumber(s.jobs_stopped_24h)}
              sub="User-requested halt"
            />
            <SystemHealth
              icon={ShieldAlert}
              tone={rateLimitTone}
              title="Rate-limit · 24h"
              value={formatNumber(s.rate_limit_events_24h)}
              sub={s.last_rate_limit_at ? `gần nhất ${relativeTime(s.last_rate_limit_at)}` : "chưa có"}
            />
            <SystemHealth
              icon={Clock}
              tone="muted"
              title="Mới tải gần nhất"
              value={relativeTime(s.last_download_at)}
              sub="lần done cuối"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// =================================================================
// Sub-components
// =================================================================

function HeroStat({
  idx, icon: Icon, title, value, sub, tone,
}: {
  idx: number;
  icon: typeof Users;
  title: string;
  value: string;
  sub: string;
  tone: "primary" | "accent" | "success" | "warning" | "destructive" | "muted";
}) {
  const toneMap: Record<typeof tone, { gradient: string; iconBg: string }> = {
    primary:    { gradient: "bg-muted",     iconBg: "bg-muted text-foreground" },
    accent:     { gradient: "bg-muted",       iconBg: "bg-muted text-foreground" },
    success:    { gradient: "bg-muted",     iconBg: "bg-muted text-success" },
    warning:    { gradient: "bg-muted",     iconBg: "bg-muted text-warning" },
    destructive:{ gradient: "bg-muted", iconBg: "bg-muted text-destructive" },
    muted:      { gradient: "bg-muted",                      iconBg: "bg-muted text-muted-foreground" },
  };
  const t = toneMap[tone];
  return (
    <Card
      
      className="group relative overflow-hidden hover:border-border transition-all hover:-translate-y-0.5 hover:fade-in-up"
      style={{ animationDelay: `${idx * 60}ms` }}
    >
      <div className={`absolute inset-0 bg-muted ${t.gradient} opacity-60 group-hover:opacity-100 transition-opacity pointer-events-none`} />
      <CardContent className="relative p-5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</span>
          <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${t.iconBg}`}>
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <div className="text-3xl font-bold tracking-tight">{value}</div>
        <div className="text-xs text-muted-foreground truncate">{sub}</div>
      </CardContent>
    </Card>
  );
}

function PlatformRow({ p }: { p: PlatformCountFE }) {
  const meta = PLATFORM_META[p.platform] || {
    label: p.platform, icon: HardDrive, gradient: "bg-muted", short: "?",
  };
  const Icon = meta.icon;
  const total = p.completed + p.failed + p.pending + p.in_flight;
  const successPct = total > 0 ? pctOf(p.completed, total) : 0;
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-md bg-muted", meta.gradient)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold flex items-center gap-2">
            {meta.label}
            <span className="text-[10px] font-mono text-muted-foreground">· {meta.short}</span>
          </div>
          <div className="text-[10px] text-muted-foreground font-mono">
            {formatNumber(p.accounts)} accounts · {formatNumber(p.files_on_disk)} files trên đĩa
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-bold">{formatBytes(p.bytes_total)}</div>
          <div className="text-[10px] text-muted-foreground">
            {p.completed_24h > 0 ? `+${p.completed_24h} trong 24h` : "24h im lặng"}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-1.5 text-center">
        <MiniPill icon={Clock}      tone="muted"     label="pending"    value={p.pending} />
        <MiniPill icon={Activity}   tone="accent"    label="running"    value={p.in_flight} />
        <MiniPill icon={CheckCircle2} tone="success" label="done"      value={p.completed} />
        <MiniPill icon={XCircle}    tone="destructive" label="failed"  value={p.failed} />
      </div>
      <div className="mt-2">
        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className={cn("h-full bg-muted", meta.gradient)}
            style={{ width: `${successPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground font-mono">
          <span>success {successPct.toFixed(0)}%</span>
          <span>{relativeTime(p.last_download_at)}</span>
        </div>
      </div>
    </div>
  );
}

function MiniPill({
  icon: Icon, tone, label, value,
}: {
  icon: typeof Clock;
  tone: "muted" | "accent" | "success" | "destructive";
  label: string;
  value: number;
}) {
  const toneCls: Record<typeof tone, string> = {
    muted:       "bg-muted text-muted-foreground",
    accent:      "bg-accent/10 text-accent",
    success:     "bg-success/10 text-success",
    destructive: "bg-destructive/10 text-destructive",
  };
  return (
    <div className={cn("rounded-md px-1.5 py-1.5 flex flex-col items-center gap-0.5", toneCls[tone])}>
      <Icon className="h-3 w-3" />
      <div className="text-sm font-bold leading-none">{formatNumber(value)}</div>
      <div className="text-[9px] uppercase tracking-wider opacity-80">{label}</div>
    </div>
  );
}

function MediaTypeRow({
  label, count, max, gradient,
}: {
  label: string;
  count: number;
  max: number;
  gradient: string;
}) {
  const p = pct(count, max);
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-semibold">{formatNumber(count)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full bg-muted transition-all", gradient)}
          style={{ width: `${p}%` }}
        />
      </div>
    </div>
  );
}

function SystemHealth({
  icon: Icon, tone, title, value, sub,
}: {
  icon: typeof Clock;
  tone: "success" | "warning" | "destructive" | "muted";
  title: string;
  value: string;
  sub: string;
}) {
  const toneCls: Record<typeof tone, string> = {
    success:     "text-success",
    warning:     "text-warning",
    destructive: "text-destructive",
    muted:       "text-muted-foreground",
  };
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
      <div className={cn("flex h-8 w-8 items-center justify-center rounded-md bg-muted", toneCls[tone])}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{title}</div>
        <div className={cn("text-base font-bold", toneCls[tone])}>{value}</div>
        <div className="text-[10px] text-muted-foreground truncate">{sub}</div>
      </div>
    </div>
  );
}

