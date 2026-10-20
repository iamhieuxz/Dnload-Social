/**
 * App Router root loading state. Shown during route transitions and
 * server-rendered Suspense boundaries.
 */
export default function GlobalLoading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-accent" />
        <p className="text-xs text-muted-foreground">Đang tải…</p>
      </div>
    </div>
  );
}
