import { cn } from "@/lib/utils";

/** Dnload Social logo mark: accent square with two parallel download arrows (plan §5). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-background",
        className
      )}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-[60%] w-[60%]"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M8 4v11" />
        <path d="m4.5 11.5 3.5 3.5 3.5-3.5" />
        <path d="M16 4v11" />
        <path d="m12.5 11.5 3.5 3.5 3.5-3.5" />
      </svg>
    </span>
  );
}
