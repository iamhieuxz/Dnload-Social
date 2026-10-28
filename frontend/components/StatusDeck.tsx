"use client";

import { useQuery } from "@tanstack/react-query";
import { Instagram, Music2, Twitter } from "lucide-react";

import { api, type DashboardStatsFE, type PlatformCountFE } from "@/lib/api";
import { cn, formatBytes, formatNumber } from "@/lib/utils";

/**
 * The whole health of the download system in one instrument panel.
 *
 * This replaces four separate cards (hero stats, disk usage, per-platform
 * queue, media-by-type): the numbers share one surface with hairline dividers
 * so they read as one reading, not as eight unrelated tiles.
 */

const PLATFORM: Record<
  string,
  { label: string; short: string; dot: string; Icon: typeof Instagram }
> = {
  instagram: { label: "Instagram", short: "IG", dot: "bg-plat-ig", Icon: Instagram },
  twitter: { label: "X / Twitter", short: "X", dot: "bg-plat-x", Icon: Twitter },
  tiktok: { label: "TikTok", short: "TT", dot: "bg-plat-tiktok", Icon: Music2 },
};

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
      {children}
    </div>
  );
}

function Cell({
  label,
  value,
  sub,
  tone = "text-ink",
}: {
  label: string;
  value: string;
  sub: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0 px-5 py-4 lg:py-5">
      <Label>{label}</Label>
      <div
        className={cn(
          "mt-2 font-display text-[28px] leading-none tracking-[-0.03em] tabular-nums lg:text-[32px]",
          tone
        )}
      >
        {value}
      </div>
      <div className="mt-2 truncate font-mono text-[10px] text-ink-3">{sub}</div>
    </div>
  );
}

/** One bar per platform: done · running · waiting · failed, in that order. */
function Segments({ p }: { p: PlatformCountFE }) {
  const total = p.completed + p.in_flight + p.pending + p.failed;
  const part = (n: number, cls: string) =>
    n > 0 ? (
      <span
        className={cn("h-full rounded-full", cls)}
        style={{ width: `${(n / (total || 1)) * 100}%` }}
      />
    ) : null;
  return (
    <div className="flex h-1.5 w-full items-stretch gap-[2px]">
      {part(p.completed, "bg-success/60")}
      {part(p.in_flight, "bg-accent")}
      {part(p.pending, "bg-white/[0.14]")}
      {part(p.failed, "bg-destructive/80")}
      {total === 0 && <span className="h-full w-full rounded-full bg-white/[0.06]" />}
    </div>
  );
}

function PlatformRow({ p }: { p: PlatformCountFE }) {
  const meta = PLATFORM[p.platform] ?? {
    label: p.platform,
    short: p.platform.slice(0, 2).toUpperCase(),
    dot: "bg-ink-3",
    Icon: Music2,
  };
  const { Icon } = meta;
  return (
    <div className="px-5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meta.dot)} />
          <Icon className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden="true" />
          <span className="truncate text-[13px] font-medium">{meta.label}</span>
          <span className="hidden shrink-0 font-mono text-[10px] text-ink-3 sm:inline">
            {formatNumber(p.accounts)} acc · {formatBytes(p.bytes_total)}
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10.5px] tabular-nums">
          <span className={p.in_flight ? "text-accent" : "text-ink-3"}>
            {formatNumber(p.in_flight)} chạy
          </span>
          <span className="text-ink-2">{formatNumber(p.pending)} chờ</span>
          <span className={p.failed ? "text-destructive" : "text-ink-3"}>
            {formatNumber(p.failed)} lỗi
          </span>
        </div>
      </div>
      <div className="mt-2">
        <Segments p={p} />
      </div>
    </div>
  );
}

function DiskCell({ s }: { s: DashboardStatsFE }) {
  const usedPct = s.disk_total_bytes
    ? Math.min(100, (s.disk_used_bytes / s.disk_total_bytes) * 100)
    : 0;
  return (
    <div className="col-span-2 min-w-0 border-t border-white/[0.06] px-5 py-4 lg:col-span-1 lg:border-l lg:border-t-0 lg:py-5">
      <Label>Ổ đĩa</Label>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="font-display text-[28px] leading-none tracking-[-0.03em] tabular-nums lg:text-[32px]">
          {formatBytes(s.disk_used_bytes)}
        </span>
        <span className="font-mono text-[10px] text-ink-3">
          / {formatBytes(s.disk_total_bytes)}
        </span>
      </div>
      <div className="mt-3 h-[3px] w-full overflow-hidden rounded-full bg-white/[0.08]">
        <div
          className="h-full rounded-full bg-accent/80 transition-all"
          style={{ width: `${usedPct}%` }}
        />
      </div>
      <div className="mt-2 font-mono text-[10px] text-ink-3">
        {formatBytes(s.disk_free_bytes)} trống
      </div>
    </div>
  );
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}s trước`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} phút trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} giờ trước`;
  return `${Math.floor(h / 24)} ngày trước`;
}

export function StatusDeck() {
  const { data: s } = useQuery<DashboardStatsFE>({
    queryKey: ["stats-dashboard"],
    queryFn: async () => (await api.get("/api/stats/dashboard")).data,
    refetchInterval: 5_000,
  });

  if (!s) {
    return (
      <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
        <div className="grid grid-cols-2 divide-x divide-white/[0.06] lg:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="space-y-3 px-5 py-5">
              <div className="h-2.5 w-20 shimmer rounded" />
              <div className="h-7 w-16 shimmer rounded" />
              <div className="h-2.5 w-28 shimmer rounded" />
            </div>
          ))}
        </div>
      </section>
    );
  }

  const queue = s.pending_count + s.in_flight_count;
  const successPct =
    s.success_rate_24h >= 0 ? Math.round(s.success_rate_24h * 100) : null;
  const platforms = s.by_platform.filter(
    (p) => p.accounts > 0 || p.pending + p.in_flight + p.completed + p.failed > 0
  );

  return (
    <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
      <div className="grid grid-cols-2 divide-x divide-white/[0.06] lg:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.15fr)]">
        <Cell
          label="Tài khoản"
          value={formatNumber(s.total_accounts)}
          sub={s.by_platform
            .filter((p) => p.accounts > 0)
            .map((p) => `${PLATFORM[p.platform]?.short ?? p.platform} ${formatNumber(p.accounts)}`)
            .join(" · ")}
        />
        <Cell
          label="Media trên đĩa"
          value={formatNumber(s.files_on_disk)}
          sub={`${formatNumber(s.folders_on_disk)} folder · ${formatBytes(
            s.disk_used_bytes
          )}`}
        />
        <Cell
          label="Hàng đợi"
          value={formatNumber(queue)}
          tone={queue > 0 ? "text-accent" : "text-ink"}
          sub={`${formatNumber(s.pending_count)} chờ · ${formatNumber(
            s.in_flight_count
          )} đang chạy`}
        />
        <Cell
          label="24 giờ"
          value={formatNumber(s.jobs_completed_24h)}
          tone={s.jobs_failed_24h > 0 ? "text-warning" : "text-success"}
          sub={`${s.jobs_failed_24h} lỗi · ${formatNumber(s.downloads_24h)} file về`}
        />
        <DiskCell s={s} />
      </div>

      <div className="divide-y divide-white/[0.06] border-t border-white/[0.06]">
        {platforms.map((p) => (
          <PlatformRow key={p.platform} p={p} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-white/[0.06] px-5 py-2.5 font-mono text-[10px] text-ink-3">
        <span>
          thành công 24h{" "}
          <span className={successPct === null ? "" : "text-ink"}>
            {successPct === null ? "—" : `${successPct}%`}
          </span>
        </span>
        <span>
          rate-limit{" "}
          <span
            className={
              s.rate_limit_events_24h === 0
                ? "text-success"
                : s.rate_limit_events_24h > 5
                  ? "text-destructive"
                  : "text-warning"
            }
          >
            {s.rate_limit_events_24h}
          </span>
        </span>
        <span className="ml-auto">
          tải gần nhất <span className="text-ink-2">{relativeTime(s.last_download_at)}</span>
        </span>
      </div>
    </section>
  );
}
