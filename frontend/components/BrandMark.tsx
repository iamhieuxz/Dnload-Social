import { cn } from "@/lib/utils";

/**
 * Dnload Social brand mark — a solid D whose counter is cut into a
 * download arrow. Straight from the brand kit in `public/brand/mark.svg`;
 * colours are fixed on purpose (accent tile, ink glyph).
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      aria-hidden="true"
      className={cn("h-8 w-8 shrink-0", className)}
    >
      <rect width="40" height="40" rx="9.6" fill="#E8C547" />
      <path
        fillRule="evenodd"
        fill="#0B0B0E"
        d="M10.2 8.8h9.6a11.2 11.2 0 0 1 0 22.4h-9.6a1.2 1.2 0 0 1-1.2-1.2v-20a1.2 1.2 0 0 1 1.2-1.2zM17.6 11.2H22.4V19.1H28.2L20 27.4L11.8 19.1H17.6Z"
      />
    </svg>
  );
}
