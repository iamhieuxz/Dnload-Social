import { BrandMark } from "@/components/BrandMark";

/**
 * App Router root loading state. Shown during route transitions and
 * server-rendered Suspense boundaries.
 */
export default function GlobalLoading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <BrandMark className="h-11 w-11" />
        <div className="h-[2px] w-24 overflow-hidden rounded-full bg-surface-3">
          <div className="loading-sweep h-full w-8 rounded-full bg-accent" />
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          Đang tải…
        </p>
      </div>
    </div>
  );
}
