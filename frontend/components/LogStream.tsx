"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobWebSocket, type LogEvent } from "@/lib/websocket";
import { Terminal } from "lucide-react";

interface Props {
  jobId: number | null;
  initialLogs?: string[];
}

const MAX_LINES = 2000;

export function LogStream({ jobId, initialLogs = [] }: Props) {
  // Lines live in state so React owns the DOM. The ref only tracks
  // the previous-line-count for auto-scroll behaviour, NOT the text.
  const [lines, setLines] = useState<string[]>(initialLogs);
  const containerRef = useRef<HTMLDivElement>(null);

  const { connected } = useJobWebSocket(jobId, (event: LogEvent) => {
    if (event.type === "log") {
      setLines((prev) => {
        const next = prev.length >= MAX_LINES ? prev.slice(prev.length - MAX_LINES + 1) : prev.slice();
        next.push(event.data.message);
        return next;
      });
    }
  });

  // Reset when switching to a different job. Without this, lines from
  // job A would leak into job B's view.
  useEffect(() => {
    setLines(initialLogs);
  }, [jobId, initialLogs]);

  // Auto-scroll only if the user is already pinned to the bottom;
  // respect their scroll position otherwise. Using a ref so the
  // effect runs on every lines change without re-binding the listener.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distFromBottom < 50) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Terminal className="h-4 w-4" /> Live logs
        </CardTitle>
        <span className={`text-xs ${connected ? "text-success" : "text-muted-foreground"}`}>
          {connected ? "● live" : "○ offline"}
        </span>
      </CardHeader>
      <CardContent>
        <div
          ref={containerRef}
          className="h-[500px] overflow-y-auto rounded-md border border-border bg-background p-3 font-mono text-xs text-foreground whitespace-pre-wrap"
        >
          {lines.join("\n")}
        </div>
      </CardContent>
    </Card>
  );
}
