"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type OverviewStats, type StorageStats } from "@/lib/api";
import { cn, formatBytes, formatNumber } from "@/lib/utils";
import {
  Users, Image, HardDrive, Activity, Clock, Download as DownloadIcon,
  Instagram, Twitter, Music2, AlertTriangle,
} from "lucide-react";

const PLATFORM_META: Record<string, { label: string; icon: typeof Users; gradient: string }> = {
  instagram: { label: "Instagram", icon: Instagram, gradient: "from-[#f09433] via-[#dc2743] to-[#bc1888]" },
  twitter:   { label: "Twitter / X", icon: Twitter, gradient: "from-[#1da1f2] via-[#0a85d0] to-black" },
  tiktok:    { label: "TikTok",     icon: Music2, gradient: "from-[#25f4ee] via-[#25f4ee] to-[#fe2c55]" },
};

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.min(100, (part / total) * 100);
}

export function StatCards() {
  const overview = useQuery<OverviewStats>({
    queryKey: ["stats-overview"],
    queryFn: async () => (await api.get("/api/stats/overview")).data,
    refetchInterval: 5_000,
  });
  const storage = useQuery<StorageStats>({
    queryKey: ["stats-storage"],
    queryFn: async () => (await api.get("/api/stats/storage")).data,
    // Disk walks are heavier than DB counts — refresh every 30s
    refetchInterval: 30_000,
  });

  if (overview.isLoading || !overview.data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} variant="glass">
            <CardContent className="p-5 space-y-3">
              <div className="h-4 w-24 shimmer rounded" />
              <div className="h-8 w-16 shimmer rounded" />
              <div className="h-3 w-32 shimmer rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const s = overview.data;
  const st = storage.data;
  const usedPct = st ? pct(st.total_disk_bytes - st.free_bytes, st.total_disk_bytes) : 0;

  return (
    <div className="space-y-4">
      {/* ----- Top row: 4 overview cards ----- */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          idx={0}
          icon={Users}
          title="Accounts"
          value={formatNumber(s.total_accounts)}
          sub={`${formatNumber(s.total_posts)} posts · ${formatNumber(s.total_stories)} stories`}
          tone="primary"
        />
        <StatCard
          idx={1}
          icon={Image}
          title="Total Media"
          value={formatNumber(s.total_media)}
          sub={`${formatNumber(s.total_highlights)} highlights indexed`}
          tone="accent"
        />
        <StatCard
          idx={2}
          icon={Clock}
          title="Pending Queue"
          value={formatNumber(s.pending_count)}
          sub={`${s.downloads_24h} added today · ${s.downloads_7d} this week`}
          tone={s.pending_count > 50 ? "warning" : "muted"}
        />
        <StatCard
          idx={3}
          icon={Activity}
          title="Jobs (24h)"
          value={`${s.jobs_completed_24h} ✓ / ${s.jobs_failed_24h} ✗`}
          sub={`${s.jobs_running} running now`}
          tone={s.jobs_failed_24h > s.jobs_completed_24h ? "destructive" : "success"}
        />
      </div>

      {/* ----- Bottom row: Disk + Per-platform breakdown ----- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* --- Disk usage card --- */}
        <Card variant="glass" className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-warning" /> Disk usage
              {st && st.total_disk_bytes > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground font-mono">
                  {formatBytes(st.total_disk_bytes - st.free_bytes)} / {formatBytes(st.total_disk_bytes)}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!st ? (
              <div className="space-y-2">
                <div className="h-3 w-full shimmer rounded" />
                <div className="h-3 w-1/2 shimmer rounded" />
              </div>
            ) : st.total_disk_bytes === 0 ? (
              <div className="text-xs text-muted-foreground py-4">
                Cannot read disk usage for this volume.
              </div>
            ) : (
              <>
                <div>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                    <span>Used</span>
                    <span className="font-mono">{usedPct.toFixed(1)}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className={cn(
                        "h-full transition-all",
                        usedPct > 90
                          ? "bg-gradient-to-r from-destructive to-rose-400"
                          : usedPct > 75
                            ? "bg-gradient-to-r from-warning to-amber-300"
                            : "bg-gradient-to-r from-primary to-accent"
                      )}
                      style={{ width: `${usedPct}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="text-lg font-bold">{formatBytes(st.total_disk_bytes - st.free_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Used</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-success">{formatBytes(st.free_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Free</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold">{formatBytes(st.total_disk_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Total</div>
                  </div>
                </div>
                {usedPct > 90 && (
                  <div className="flex items-center gap-2 rounded-md bg-destructive/10 border border-destructive/30 px-2.5 py-1.5 text-[11px] text-destructive">
                    <AlertTriangle className="h-3 w-3" />
                    <span>Disk almost full — clean up old media or change <span className="font-mono">download_folder</span> in <span className="font-mono">.env</span>.</span>
                  </div>
                )}
                <div className="pt-3 border-t border-white/5 grid grid-cols-2 gap-3 text-center">
                  <div>
                    <div className="text-sm font-bold">{formatNumber(st.total_files)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Files on disk</div>
                  </div>
                  <div>
                    <div className="text-sm font-bold">{formatBytes(st.total_size_bytes)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">In download folders</div>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* --- Per-platform disk breakdown --- */}
        <Card variant="glass" className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <DownloadIcon className="h-4 w-4 text-primary" /> Storage by platform
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!st ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 shimmer rounded" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {st.by_platform.map((b) => {
                  const meta = PLATFORM_META[b.platform] || {
                    label: b.platform, icon: HardDrive, gradient: "from-zinc-500 to-zinc-700",
                  };
                  const Icon = meta.icon;
                  const p = pct(b.size_bytes, st.total_size_bytes);
                  return (
                    <div key={b.platform} className="rounded-lg border border-white/5 bg-black/20 p-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className={cn("flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br", meta.gradient)}>
                          <Icon className="h-3.5 w-3.5 text-white" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium">{meta.label}</div>
                          <div className="text-[10px] text-muted-foreground font-mono truncate" title={b.path}>
                            {b.path}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-bold">{formatBytes(b.size_bytes)}</div>
                          <div className="text-[10px] text-muted-foreground">{p.toFixed(1)}%</div>
                        </div>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className={cn("h-full bg-gradient-to-r", meta.gradient)}
                          style={{ width: `${p}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between mt-1.5 text-[10px] text-muted-foreground font-mono">
                        <span>{formatNumber(b.file_count)} files</span>
                        <span>{formatNumber(b.folder_count)} folders</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({
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
    primary:    { gradient: "from-primary/20 via-primary/5 to-transparent",     iconBg: "bg-primary/20 text-primary" },
    accent:     { gradient: "from-accent/20 via-accent/5 to-transparent",       iconBg: "bg-accent/20 text-accent" },
    success:    { gradient: "from-success/20 via-success/5 to-transparent",     iconBg: "bg-success/20 text-success" },
    warning:    { gradient: "from-warning/20 via-warning/5 to-transparent",     iconBg: "bg-warning/20 text-warning" },
    destructive:{ gradient: "from-destructive/20 via-destructive/5 to-transparent", iconBg: "bg-destructive/20 text-destructive" },
    muted:      { gradient: "from-white/5 to-transparent",                      iconBg: "bg-white/10 text-muted-foreground" },
  };
  const t = toneMap[tone];
  return (
    <Card
      variant="glass"
      className="group relative overflow-hidden hover:border-white/20 transition-all hover:-translate-y-0.5 hover:shadow-glow-sm fade-in-up"
      style={{ animationDelay: `${idx * 60}ms` }}
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${t.gradient} opacity-60 group-hover:opacity-100 transition-opacity pointer-events-none`} />
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
