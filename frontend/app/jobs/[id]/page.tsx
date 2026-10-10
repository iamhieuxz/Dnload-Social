"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { api, type Job } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LogStream } from "@/components/LogStream";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { ArrowLeft, StopCircle, Trash2 } from "lucide-react";
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

  if (!job) return <div>Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/jobs")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h2 className="text-2xl font-bold">Job #{job.id}</h2>
            <div className="flex items-center gap-2 mt-1">
              <JobStatusBadge status={job.status} />
              <span className="text-sm text-muted-foreground">{job.job_type}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {job.status === "running" && (
            <Button variant="destructive" onClick={() => stop.mutate()}>
              <StopCircle className="h-4 w-4" /> Stop
            </Button>
          )}
          {job.status !== "running" && (
            <Button variant="outline" onClick={() => remove.mutate()}>
              <Trash2 className="h-4 w-4" /> Delete
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "New files", value: job.new_files_count },
          { label: "Total processed", value: job.total_processed },
          { label: "Duration", value: formatDuration(job.duration_seconds) },
          { label: "Targets", value: job.targets ? JSON.parse(job.targets).length : 0 },
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

      <LogStream jobId={job.status === "running" || job.status === "queued" ? id : id} initialLogs={logsData?.lines} />
    </div>
  );
}
