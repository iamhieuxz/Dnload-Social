"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { formatDuration } from "@/lib/utils";
import { useState } from "react";
import { History, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_FILTERS = ["", "queued", "running", "completed", "stopped", "failed"] as const;

const STATUS_TABS: Record<string, string> = {
  "": "All",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  stopped: "Stopped",
  failed: "Failed",
};

export default function JobsPage() {
  const [page] = useState(1);
  const [status, setStatus] = useState<string>("");

  const { data } = useQuery({
    queryKey: ["jobs", page, status],
    queryFn: async () =>
      (
        await api.get("/api/jobs", {
          params: { page, page_size: 30, status: status || undefined },
        })
      ).data,
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">Job history</span>
        </h2>
        <p className="text-muted-foreground mt-1">
          {data?.total ?? 0} jobs recorded
        </p>
      </div>

      <Card variant="glass" className="p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="h-4 w-4 text-muted-foreground" />
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                status === s
                  ? "bg-gradient-to-r from-primary to-accent text-white shadow-glow-sm"
                  : "bg-white/5 text-muted-foreground hover:bg-white/10 hover:text-foreground"
              )}
            >
              {STATUS_TABS[s]}
            </button>
          ))}
        </div>
      </Card>

      <Card variant="glass">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Recent jobs
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-white/5">
            {!data?.items.length ? (
              <div className="p-12 text-center text-muted-foreground">No jobs found</div>
            ) : (
              data?.items.map((j: Job, i: number) => (
                <Link
                  key={j.id}
                  href={`/jobs/${j.id}`}
                  className="flex items-center gap-4 p-4 hover:bg-white/5 transition-colors group fade-in-up"
                  style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-gradient-to-br from-primary/20 to-accent/20 font-mono text-sm font-bold">
                    #{j.id}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{j.job_type}</span>
                      <JobStatusBadge status={j.status} />
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {new Date(j.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="hidden md:flex items-center gap-6 text-xs">
                    <div className="text-right">
                      <div className="text-muted-foreground">New</div>
                      <div className="font-mono font-medium text-success">{j.new_files_count}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-muted-foreground">Processed</div>
                      <div className="font-mono font-medium">{j.total_processed}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-muted-foreground">Duration</div>
                      <div className="font-mono font-medium">{formatDuration(j.duration_seconds)}</div>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
