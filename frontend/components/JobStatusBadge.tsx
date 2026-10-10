"use client";

import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, XCircle, StopCircle, Clock } from "lucide-react";
import type { JobStatus } from "@/lib/api";

const map: Record<JobStatus, { variant: any; label: string; icon: any }> = {
  queued: { variant: "secondary", label: "Queued", icon: Clock },
  running: { variant: "warning", label: "Running", icon: Loader2 },
  completed: { variant: "success", label: "Completed", icon: CheckCircle2 },
  stopped: { variant: "outline", label: "Stopped", icon: StopCircle },
  failed: { variant: "destructive", label: "Failed", icon: XCircle },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const conf = map[status];
  const Icon = conf.icon;
  return (
    <Badge variant={conf.variant} className="gap-1">
      <Icon className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`} />
      {conf.label}
    </Badge>
  );
}
