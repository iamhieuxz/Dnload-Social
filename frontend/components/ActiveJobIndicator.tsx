"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Job } from "@/lib/api";
import { useSystemWebSocket, type LogEvent } from "@/lib/websocket";
import { Loader2, ChevronRight } from "lucide-react";
import Link from "next/link";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { formatDuration } from "@/lib/utils";

export function ActiveJobIndicator() {
  const queryClient = useQueryClient();

  useSystemWebSocket((event: LogEvent) => {
    if (event.type === "job_update" || event.type === "status") {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["stats-overview"] });
    }
  });

  // One job per platform can run at once, so this reads the list rather than
  // /api/jobs/active — that endpoint returns a single job and would hide the
  // other stream while Instagram and X download together.
  const { data } = useQuery<{ items: Job[] }>({
    queryKey: ["jobs", "running"],
    queryFn: async () =>
      (await api.get("/api/jobs", { params: { status: "running", page_size: 10 } })).data,
    // 3s tick handles elapsed display. Sidebar also polls at 5s — the
    // `refetchInterval` here keeps this component self-sufficient
    // (it can render before Sidebar mounts).
    refetchInterval: 3_000,
  });

  const jobs = data?.items ?? [];
  if (!jobs.length) return null;
  const job = jobs[0];
  const extra = jobs.length - 1;
  // Re-render every 3s via refetchInterval already gives us a fresh
  // `Date.now()`. No separate `setInterval` needed.
  const elapsed = job.started_at
    ? Math.floor((Date.now() - new Date(job.started_at).getTime()) / 1000)
    : 0;

  return (
    <Link
      href={extra > 0 ? "/jobs" : `/jobs/${job.id}`}
      className="group relative flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 hover:border-primary/50 transition-colors"
      title={extra > 0 ? `${jobs.length} job đang chạy` : undefined}
    >
      <div className="relative flex h-8 w-8 items-center justify-center rounded-md bg-muted">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      </div>
      <div className="relative text-sm">
        <div className="font-semibold flex items-center gap-2">
          Job <span className="text-primary">#{job.id}</span>
          {extra > 0 && (
            <span className="rounded-full border border-primary/40 px-1.5 font-mono text-[10px] font-normal text-primary">
              +{extra} luồng
            </span>
          )}
          <span className="text-xs text-muted-foreground">·</span>
          <span className="text-xs font-mono">{job.new_files_count} new</span>
        </div>
        <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
          <JobStatusBadge status={job.status} />
          <span>· {formatDuration(elapsed)}</span>
        </div>
      </div>
      <ChevronRight className="relative h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
    </Link>
  );
}
