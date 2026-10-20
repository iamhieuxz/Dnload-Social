import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface BulkActionBarProps {
  count: number;
  onClear: () => void;
  children: ReactNode;
  className?: string;
}

/**
 * Bottom-anchored action bar that slides up when rows are selected (plan §6.2).
 * Renders a translucent surface + a monospace count + the actions passed in.
 */
export function BulkActionBar({ count, onClear, children, className }: BulkActionBarProps) {
  if (count === 0) return null;
  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className={cn(
        "fixed inset-x-0 bottom-4 z-30 mx-auto flex w-fit max-w-[min(100%-2rem,640px)] items-center gap-3 rounded-palette border border-border bg-surface-1/95 px-4 py-2 shadow-float backdrop-blur-md fade-in-up",
        className
      )}
    >
      <span className="font-mono text-sm text-ink">
        <span className="text-accent">{count}</span> đã chọn
      </span>
      <span className="h-5 w-px bg-border" />
      <div className="flex items-center gap-1">{children}</div>
      <span className="h-5 w-px bg-border" />
      <button
        type="button"
        onClick={onClear}
        className="rounded-md px-2 py-1 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
      >
        Bỏ chọn
      </button>
    </div>
  );
}
