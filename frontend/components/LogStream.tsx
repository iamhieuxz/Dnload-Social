"use client";

import { useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobWebSocket, type LogEvent } from "@/lib/websocket";
import { Terminal } from "lucide-react";

interface Props {
  jobId: number | null;
  initialLogs?: string[];
}

export function LogStream({ jobId, initialLogs = [] }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const linesRef = useRef<string[]>(initialLogs);

  const { connected } = useJobWebSocket(jobId, (event: LogEvent) => {
    if (event.type === "log") {
      linesRef.current = [...linesRef.current, event.data.message].slice(-2000);
      render();
    }
  });

  useEffect(() => {
    if (jobId) {
      linesRef.current = [];
      render();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  function render() {
    if (!containerRef.current) return;
    const wasAtBottom =
      containerRef.current.scrollHeight - containerRef.current.scrollTop - containerRef.current.clientHeight < 50;
    containerRef.current.innerText = linesRef.current.join("\n");
    if (wasAtBottom) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }

  useEffect(() => {
    render();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialLogs]);

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
          className="h-[500px] overflow-y-auto rounded-md bg-black p-3 font-mono text-xs text-zinc-100 whitespace-pre-wrap"
        />
      </CardContent>
    </Card>
  );
}
