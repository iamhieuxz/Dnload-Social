import { cn } from "@/lib/utils";

const STATUS: Record<string, { cls: string; label: string; pulse?: boolean }> = {
  completed: { cls: "bg-success", label: "Hoàn tất" },
  downloading: { cls: "bg-info", label: "Đang tải", pulse: true },
  failed: { cls: "bg-destructive", label: "Lỗi" },
  pending: { cls: "bg-muted-foreground", label: "Chờ" },
  skipped: { cls: "bg-muted-foreground/50", label: "Bỏ qua" },
};

/** 8px status dot that replaces long status badges in tables (plan §6.2). */
export function StatusDot({ status, className }: { status: string; className?: string }) {
  const s = STATUS[status] ?? STATUS.pending;
  return (
    <span
      role="img"
      aria-label={s.label}
      title={s.label}
      className={cn("relative inline-flex h-2 w-2 shrink-0 rounded-full", s.cls, className)}
    >
      {s.pulse && (
        <span className="absolute inset-0 animate-ping rounded-full bg-info opacity-60" />
      )}
    </span>
  );
}
