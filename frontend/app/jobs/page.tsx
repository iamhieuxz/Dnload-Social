"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { formatDuration } from "@/lib/utils";
import { useState } from "react";
import { History, Filter, Inbox } from "lucide-react";
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
    // Only poll while a job is running/queued — once everything is
    // terminal the list is stable and we can save the request budget.
    refetchInterval: (query) => {
      const items = (query.state.data?.items ?? []) as Job[];
      return items.some((j) => j.status === "running" || j.status === "queued") ? 5_000 : false;
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Job history"
        description={`${data?.total ?? 0} jobs recorded`}
      />

      <Card className="p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="h-4 w-4 text-muted-foreground" />
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={cn(
                "tab-type px-3 py-1.5 rounded-md transition-colors border",
                status === s
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {STATUS_TABS[s]}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4" />
            Recent jobs
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {!data?.items.length ? (
            <EmptyState
              icon={Inbox}
              title="Chưa có job nào"
              description={
                status
                  ? `Không có job nào ở trạng thái "${STATUS_TABS[status]}".`
                  : "Chạy một job từ Dashboard để bắt đầu."
              }
              className="border-0"
            />
          ) : (
            <div className="divide-y divide-border">
              {data?.items.map((j: Job, i: number) => (
                <Link
                  key={j.id}
                  href={`/jobs/${j.id}`}
                  className="flex items-center gap-4 p-4 hover:bg-muted/50 transition-colors group fade-in-up"
                  style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted font-mono text-sm font-bold">
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
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
