import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

/** Empty list placeholder with one clear next step (plan §8). */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-border px-6 py-12 text-center",
        className
      )}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-sm font-medium text-foreground">{title}</div>
        {description && (
          <div className="mt-1 max-w-sm text-xs text-muted-foreground">{description}</div>
        )}
      </div>
      {action}
    </div>
  );
}
