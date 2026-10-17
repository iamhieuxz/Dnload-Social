"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { api, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LogStream } from "@/components/LogStream";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { PageHeader } from "@/components/PageHeader";
import { ArrowLeft, StopCircle, Trash2, Loader2 } from "lucide-react";
import { formatDuration } from "@/lib/utils";
import { toast } from "sonner";

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const id = parseInt(params.id, 10);
  const router = useRouter();
  const qc = useQueryClient();

  const { data: job } = useQuery<Job>({
    queryKey: ["job", id],
    queryFn: async () => (await api.get(`/api/jobs/${id}`)).data,
    refetchInterval: 3_000,
  });

  const { data: logsData } = useQuery<{ lines: string[] }>({
    queryKey: ["job-logs", id],
    queryFn: async () => (await api.get(`/api/jobs/${id}/logs`, { params: { limit: 1000 } })).data,
    enabled: !!job,
    refetchInterval: 3_000,
  });

  const stop = useMutation({
    mutationFn: async () => (await api.post(`/api/jobs/${id}/stop`)).data,
    onSuccess: () => {
      toast.success("Stop requested");
      qc.invalidateQueries({ queryKey: ["job", id] });
    },
  });

  const remove = useMutation({
    mutationFn: async () => (await api.delete(`/api/jobs/${id}`)).data,
    onSuccess: () => {
      toast.success("Job deleted");
      router.push("/jobs");
    },
  });

  if (!job) {
    return (
      <div className="flex items-center gap-2 p-12 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Đang tải job…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={`Job #${job.id}`}
        description={
          <span className="flex items-center gap-2 flex-wrap">
            <JobStatusBadge status={job.status} />
            <span>{job.job_type}</span>
          </span>
        }
        actions={
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => router.push("/jobs")} className="gap-1.5">
              <ArrowLeft className="h-3.5 w-3.5" /> Quay lại
            </Button>
            {job.status === "running" && (
              <Button variant="destructive" size="sm" onClick={() => stop.mutate()} className="gap-1.5">
                <StopCircle className="h-3.5 w-3.5" /> Stop
              </Button>
            )}
            {job.status !== "running" && (
              <Button variant="outline" size="sm" onClick={() => remove.mutate()} className="gap-1.5">
                <Trash2 className="h-3.5 w-3.5" /> Xoá
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "New files", value: job.new_files_count },
          { label: "Total processed", value: job.total_processed },
          { label: "Duration", value: formatDuration(job.duration_seconds) },
          { label: "Targets", value: (() => { try { return job.targets ? JSON.parse(job.targets).length : 0; } catch { return 0; } })() },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="p-4">
              <div className="text-sm text-muted-foreground">{s.label}</div>
              <div className="text-2xl font-bold">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {job.error_message && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive text-base">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-destructive whitespace-pre-wrap">{job.error_message}</pre>
          </CardContent>
        </Card>
      )}

      <LogStream jobId={id} initialLogs={logsData?.lines} />
    </div>
  );
}
