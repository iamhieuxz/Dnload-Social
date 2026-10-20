import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="flex max-w-md flex-col items-center gap-3 rounded-card border border-dashed border-border px-6 py-12 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Compass className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">Trang không tồn tại</div>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">
            Đường dẫn bạn mở không khớp với route nào. Có thể đã bị đổi tên trong lúc redesign.
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
        >
          Về Dashboard
        </Link>
      </div>
    </div>
  );
}
