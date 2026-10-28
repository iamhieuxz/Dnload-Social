"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Square } from "lucide-react";
import { toast } from "sonner";

import { api, type DownloadPlatform, type Job } from "@/lib/api";
import { cn, formatDuration, formatNumber } from "@/lib/utils";

/**
 * "What is running, and what can I start next" in one block.
 *
 * Instagram and X run at the same time now, so this lists every running job
 * (the old dashboard showed only the newest one from /api/jobs/active and
 * silently hid the other stream).
 */

interface PendingSummary {
  platform: string;
  pending: number;
  in_flight: number;
  resumable: number;
}

const PLATFORMS: { key: DownloadPlatform; label: string; short: string; dot: string }[] = [
  { key: "instagram", label: "Instagram", short: "IG", dot: "bg-plat-ig" },
  { key: "twitter", label: "X / Twitter", short: "X", dot: "bg-plat-x" },
  { key: "tiktok", label: "TikTok", short: "TT", dot: "bg-plat-tiktok" },
];

function platformOf(job: Job): string {
  let targets: string[] = [];
  try {
    targets = job.targets ? JSON.parse(job.targets) : [];
  } catch {
    targets = [];
  }
  const t = targets.join(" ").toLowerCase();
  if (t.includes("instagram.com")) return "instagram";
  if (t.includes("twitter.com") || t.includes("x.com")) return "twitter";
  if (t.includes("tiktok.com")) return "tiktok";
  return "unknown";
}

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function elapsedSeconds(job: Job, now: number): number {
  if (!job.started_at) return 0;
  return Math.max(0, Math.floor((now - new Date(job.started_at).getTime()) / 1000));
}

export function ControlRail() {
  const qc = useQueryClient();
  const now = useNow(1000);

  const jobs = useQuery<{ items: Job[]; total: number }>({
    queryKey: ["jobs", "running"],
    queryFn: async () =>
      (await api.get("/api/jobs", { params: { status: "running", page_size: 10 } })).data,
    refetchInterval: 3_000,
  });

  const summaries = useQuery<Record<string, PendingSummary>>({
    queryKey: ["pending-summary-all"],
    queryFn: async () => {
      const [ig, tw, tt] = await Promise.all(
        PLATFORMS.map((p) =>
          api.get("/api/downloads/pending-summary", { params: { platform: p.key } })
        )
      );
      return { instagram: ig.data, twitter: tw.data, tiktok: tt.data };
    },
    refetchInterval: 5_000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["jobs"] });
    qc.invalidateQueries({ queryKey: ["stats-dashboard"] });
    qc.invalidateQueries({ queryKey: ["pending-summary-all"] });
    qc.invalidateQueries({ queryKey: ["downloads"] });
  };

  const stopMut = useMutation({
    mutationFn: async (jobId: number) => (await api.post(`/api/jobs/${jobId}/stop`)).data,
    onSuccess: () => {
      toast.success("Đã gửi lệnh dừng — row đang chạy sẽ về hàng đợi");
      invalidate();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Không dừng được job"),
  });

  const runMut = useMutation({
    mutationFn: async (platform: DownloadPlatform) =>
      (await api.post("/api/downloads/run-pending", null, { params: { platform } })).data,
    onSuccess: (res: { marked: number }) => {
      if (!res?.marked) toast.info("Hàng đợi của nền tảng này đã trống");
      else toast.success(`Đã nhận ${res.marked} mục vào job mới`);
      invalidate();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Không chạy tiếp được"),
  });

  const running = jobs.data?.items ?? [];
  const runningPlatforms = new Set(running.map(platformOf));
  const resumableOf = (p: string) => summaries.data?.[p]?.resumable ?? 0;
  const totalResumable = PLATFORMS.reduce((sum, p) => sum + resumableOf(p.key), 0);

  // Render the same shell the server rendered until both queries have an
  // answer; otherwise the numbers flip from 0 to the real value during
  // hydration (React logs a mismatch and re-renders the whole tree).
  if (!jobs.data || !summaries.data) {
    return (
      <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
        <header className="flex items-baseline justify-between gap-3 px-5 pb-1 pt-4">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Đang chạy
          </h2>
          <span className="font-mono text-[10px] text-ink-3">—</span>
        </header>
        <div className="space-y-2 px-5 py-4">
          <div className="h-3 w-40 shimmer rounded" />
          <div className="h-3 w-28 shimmer rounded" />
        </div>
      </section>
    );
  }

  return (
    <section className="fade-in-up overflow-hidden rounded-[14px] border border-white/[0.07] bg-card">
      <header className="flex items-baseline justify-between gap-3 px-5 pb-1 pt-4">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Đang chạy
        </h2>
        <span className="font-mono text-[10px] text-ink-3">
          {running.length} luồng
        </span>
      </header>

      {running.length === 0 ? (
        <p className="px-5 py-4 text-xs text-ink-3">
          {totalResumable > 0
            ? `${formatNumber(totalResumable)} mục đang chờ — bấm chạy tiếp bên dưới.`
            : "Không có job nào đang chạy."}
        </p>
      ) : (
        <ul className="divide-y divide-white/[0.05]">
          {running.map((job) => {
            const key = platformOf(job);
            const meta = PLATFORMS.find((p) => p.key === key);
            return (
              <li key={job.id} className="flex items-center gap-3 px-5 py-3">
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent/30" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[13px] font-medium">
                      {meta?.label ?? "Job"}
                    </span>
                    <span className="font-mono text-[10px] text-ink-3">#{job.id}</span>
                  </div>
                  <div className="mt-0.5 font-mono text-[10.5px] tabular-nums text-ink-2">
                    {formatNumber(job.new_files_count)} file ·{" "}
                    {formatDuration(elapsedSeconds(job, now))} ·{" "}
                    {formatNumber(job.total_processed)} account
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => stopMut.mutate(job.id)}
                  disabled={stopMut.isPending}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md border border-destructive/30 px-2 font-mono text-[10px] uppercase tracking-wider text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                >
                  {stopMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Square className="h-3 w-3" />
                  )}
                  Dừng
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="border-t border-white/[0.06] px-5 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
            Chạy tiếp hàng đợi
          </span>
          <span className="font-mono text-[10px] tabular-nums text-ink-3">
            {formatNumber(totalResumable)} mục
          </span>
        </div>
        <div className="mt-2.5 grid grid-cols-3 gap-2">
          {PLATFORMS.map((p) => {
            const count = resumableOf(p.key);
            const isRunning = runningPlatforms.has(p.key);
            const busy = runMut.isPending && runMut.variables === p.key;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => runMut.mutate(p.key)}
                disabled={isRunning || count === 0 || busy}
                title={
                  isRunning
                    ? `${p.label} đang chạy — dừng job hiện tại trước`
                    : `${count} mục sẵn sàng cho ${p.label}`
                }
                className={cn(
                  "flex h-8 items-center justify-center gap-1.5 rounded-md border font-mono text-[10px] uppercase tracking-wider transition-colors",
                  isRunning || count === 0
                    ? "border-white/[0.07] text-ink-3"
                    : "border-accent/40 bg-accent/10 text-accent hover:bg-accent/15"
                )}
              >
                {busy ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : isRunning ? (
                  <span className={cn("h-1.5 w-1.5 rounded-full", p.dot)} />
                ) : (
                  <Play className="h-3 w-3" />
                )}
                {p.short}
                <span className="tabular-nums opacity-70">{formatNumber(count)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
