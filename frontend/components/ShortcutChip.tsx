import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Mono keyboard hint chip, e.g. ⌘K or ↵ (plan §3, §7). */
export function ShortcutChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-surface-2 px-1.5 font-mono text-[11px] text-ink-2",
        className
      )}
    >
      {children}
    </kbd>
  );
}
