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
      queryClient.invalidateQueries({ queryKey: ["active-job"] });
      queryClient.invalidateQueries({ queryKey: ["stats-overview"] });
    }
  });

  const { data } = useQuery<{ job: Job | null }>({
    queryKey: ["active-job"],
    queryFn: async () => (await api.get("/api/jobs/active")).data,
    // 3s tick handles elapsed display. Sidebar also polls at 5s — the
    // `refetchInterval` here keeps this component self-sufficient
    // (it can render before Sidebar mounts).
    refetchInterval: 3_000,
  });

  if (!data?.job) return null;
  const job = data.job;
  // Re-render every 3s via refetchInterval already gives us a fresh
  // `Date.now()`. No separate `setInterval` needed.
  const elapsed = Math.floor((Date.now() - new Date(job.started_at!).getTime()) / 1000);

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="group relative flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 hover:border-primary/50 transition-colors"
    >
      <div className="relative flex h-8 w-8 items-center justify-center rounded-md bg-muted">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      </div>
      <div className="relative text-sm">
        <div className="font-semibold flex items-center gap-2">
          Job <span className="text-primary">#{job.id}</span>
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
