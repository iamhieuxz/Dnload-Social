"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type DashboardStatsFE } from "@/lib/api";
import { cn, formatBytes, formatNumber } from "@/lib/utils";

/**
 * Who is worth downloading next. Sizes come from the last disk scan, so this
 * doubles as the ranking the queue is claimed in (biggest account first).
 * Shares the ["stats-dashboard"] cache entry with StatusDeck — one request.
 */

const BAR: Record<string, string> = {
  instagram: "bg-plat-ig/70",
  twitter: "bg-plat-x/70",
  tiktok: "bg-plat-tiktok/70",
};

export function TopAccounts() {
  const { data } = useQuery<DashboardStatsFE>({
    queryKey: ["stats-dashboard"],
    queryFn: async () => (await api.get("/api/stats/dashboard")).data,
    refetchInterval: 5_000,
  });

  const rows = (data?.top_accounts_by_size ?? []).slice(0, 6);
  const max = rows[0]?.total_size_bytes || 1;

  return (
    <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
      <header className="flex items-baseline justify-between gap-3 px-5 pb-2 pt-4">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Dung lượng lớn nhất
        </h2>
        <span className="font-mono text-[10px] text-ink-3">theo lần quét gần nhất</span>
      </header>

      {rows.length === 0 ? (
        <p className="px-5 pb-5 pt-1 text-xs text-ink-3">
          Chưa quét tài khoản nào. Chạy <span className="font-mono">Accounts → Quét lại</span>{" "}
          để có bảng xếp hạng.
        </p>
      ) : (
        <ol className="divide-y divide-white/[0.05] pb-1">
          {rows.map((a, i) => (
            <li
              key={a.id}
              className="grid grid-cols-[1.4rem_minmax(0,1fr)_auto] items-center gap-3 px-5 py-2.5"
            >
              <span className="font-mono text-[10px] tabular-nums text-ink-3">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="truncate text-[13px] font-medium">@{a.username}</span>
                  <span className="shrink-0 font-mono text-[10px] text-ink-3">
                    {formatNumber(a.total_posts)} post
                  </span>
                </div>
                <div className="mt-1.5 h-[2px] w-full overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className={cn("h-full rounded-full", BAR[a.platform] ?? "bg-accent/60")}
                    style={{ width: `${Math.max(2, (a.total_size_bytes / max) * 100)}%` }}
                  />
                </div>
              </div>
              <span className="font-mono text-[11px] tabular-nums text-ink-2">
                {formatBytes(a.total_size_bytes)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
