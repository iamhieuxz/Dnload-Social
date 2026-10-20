import { cn } from "@/lib/utils";

const PLATFORM_DOT: Record<string, string> = {
  instagram: "bg-plat-ig",
  twitter: "bg-plat-x",
  tiktok: "bg-plat-tiktok",
};

/** 6px platform accent dot — the only place a platform color appears in a row (plan §11). */
export function PlatformDot({ platform, className }: { platform: string; className?: string }) {
  return (
    <span
      role="img"
      aria-label={platform}
      title={platform}
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        PLATFORM_DOT[platform] ?? "bg-muted-foreground",
        className
      )}
    />
  );
}
