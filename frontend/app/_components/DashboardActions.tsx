"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type JobCreate, type JobType } from "@/lib/api";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Play, Loader2 } from "lucide-react";

interface Props {
  title: string;
  description: string;
  icon: React.ReactNode;
  target: JobType;
  gradient?: string;
  iconBg?: string;
  delay?: number;
}

export function DashboardActions({
  title,
  description,
  icon,
  target,
  gradient = "from-primary/20 to-transparent",
  iconBg = "bg-primary/20 text-primary",
  delay = 0,
}: Props) {
  const [input, setInput] = useState("");
  const [includePosts, setIncludePosts] = useState(true);
  const [includeStories, setIncludeStories] = useState(true);
  const [includeHighlights, setIncludeHighlights] = useState(false);
  const router = useRouter();
  const qc = useQueryClient();

  const createJob = useMutation({
    mutationFn: async (payload: JobCreate) => (await api.post("/api/jobs", payload)).data,
    onSuccess: (job) => {
      toast.success(`Job #${job.id} created`);
      qc.invalidateQueries({ queryKey: ["active-job"] });
      router.push(`/jobs/${job.id}`);
    },
    onError: (e: any) => {
      toast.error(e?.response?.data?.detail ?? "Failed to create job");
    },
  });

  function submit() {
    const targets =
      target === "update_list"
        ? input.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
        : target === "add_new"
        ? [input.trim()]
        : [];

    createJob.mutate({
      job_type: target,
      targets,
      include_posts: includePosts,
      include_stories: includeStories,
      include_highlights: includeHighlights,
      disable_range: true,
    });
  }

  return (
    <Card
      variant="glass"
      className="group relative overflow-hidden hover:border-white/20 transition-all hover:-translate-y-0.5 fade-in-up"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div
        className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none`}
      />
      <div className="relative p-5 space-y-3">
        <div className="flex items-start gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${iconBg}`}>{icon}</div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold">{title}</div>
            <div className="text-sm text-muted-foreground">{description}</div>
          </div>
        </div>

        {target !== "update_all" && (
          <div>
            {target === "add_new" ? (
              <Input
                placeholder="username or post URL"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="bg-background/50"
              />
            ) : (
              <Textarea
                placeholder="One username or URL per line"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={4}
                className="bg-background/50 font-mono text-xs"
              />
            )}
          </div>
        )}

        {target === "update_list" && (
          <div className="flex items-center gap-3 text-sm">
            <label className="flex items-center gap-1.5 cursor-pointer hover:text-foreground">
              <input
                type="checkbox"
                checked={includePosts}
                onChange={(e) => setIncludePosts(e.target.checked)}
                className="accent-primary"
              />
              Posts
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer hover:text-foreground">
              <input
                type="checkbox"
                checked={includeStories}
                onChange={(e) => setIncludeStories(e.target.checked)}
                className="accent-primary"
              />
              Stories
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer hover:text-foreground">
              <input
                type="checkbox"
                checked={includeHighlights}
                onChange={(e) => setIncludeHighlights(e.target.checked)}
                className="accent-primary"
              />
              Highlights
            </label>
          </div>
        )}

        <Button
          onClick={submit}
          disabled={createJob.isPending}
          className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90 text-white shadow-glow-sm"
        >
          {createJob.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Run job
        </Button>
      </div>
    </Card>
  );
}
