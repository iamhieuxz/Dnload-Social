import type { DownloadPlatform } from "@/lib/api";

export interface DetectedUrl {
  url: string;
  platform: DownloadPlatform | null;
  /** Default content type for the platform; IG may be expanded by the user. */
  contentType: "post" | "story" | "highlight" | "tweet" | "tiktok" | null;
  author: string | null;
}

/** Map a pasted URL to a platform. Returns null when the host is not supported. */
export function detectPlatform(raw: string): DownloadPlatform | null {
  const u = raw.trim().toLowerCase();
  if (!u) return null;
  if (/(^|\/\/|\.)instagram\.com\//.test(u)) return "instagram";
  if (/(^|\/\/|\.)(twitter\.com|x\.com)\//.test(u)) return "twitter";
  if (/(^|\/\/|\.)(tiktok\.com|vm\.tiktok\.com)\b/.test(u)) return "tiktok";
  return null;
}

/** Author from a URL: TikTok @name, IG /<user>/ or /p/<code>, X /<user>/status/<id>. */
export function authorOf(raw: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(raw.trim());
  } catch {
    return null;
  }
  const at = parsed.pathname.match(/@([\w.-]+)/)?.[1];
  if (at) return at;
  const rest = parsed.pathname.split("/").filter(Boolean);
  if (!rest.length) return null;
  if (rest[0] === "stories" && rest.length > 1) return rest[1];
  if (["p", "reel", "reels", "stories", "status", "i"].includes(rest[0])) return null;
  return rest[0] ?? null;
}

function contentTypeOf(url: URL, platform: DownloadPlatform): DetectedUrl["contentType"] {
  const path = url.pathname.toLowerCase();
  if (platform === "instagram") {
    if (path.includes("/stories/highlights/")) return "highlight";
    if (path.startsWith("/stories/")) return "story" as DetectedUrl["contentType"];
    if (/^\/(p|reel|reels)\//.test(path)) return "post";
    return null;
  }
  return platform === "twitter" ? "tweet" : "tiktok";
}

export function detectUrl(raw: string): DetectedUrl | null {
  const url = raw.trim();
  if (!url) return null;
  const platform = detectPlatform(url);
  if (!platform) return { url, platform: null, contentType: null, author: null };
  let parsed: URL;
  try { parsed = new URL(url); } catch { return { url, platform: null, contentType: null, author: null }; }
  const contentType = contentTypeOf(parsed, platform);
  return { url, platform, contentType, author: authorOf(url) };
}
