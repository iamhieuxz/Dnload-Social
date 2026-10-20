"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * App Router root error boundary — catches uncaught throws from any
 * client component below app/. Renders a self-contained recovery UI
 * so one bad page doesn't kill the whole app.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to browser console for dev; production logging is out of scope.
    console.error("App error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="flex max-w-md flex-col items-center gap-3 rounded-card border border-dashed border-border px-6 py-12 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">Đã xảy ra lỗi</div>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">
            {error.message || "Lỗi không xác định"}
            {error.digest && (
              <span className="mt-1 block font-mono text-[10px] text-muted-foreground/70">
                digest: {error.digest}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reset}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
          >
            <RotateCw className="h-3.5 w-3.5" />
            Thử lại
          </button>
          <Link
            href="/"
            className="inline-flex items-center rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
          >
            Về Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
