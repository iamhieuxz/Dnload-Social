import { describe, expect, it } from "vitest";
import { detectUrl, detectPlatform } from "./detect";

describe("detectPlatform", () => {
  const cases: [string, string | null][] = [
    ["https://www.instagram.com/p/ABC123/", "instagram"],
    ["https://instagram.com/user1", "instagram"],
    ["https://instagram.com/stories/user1/123", "instagram"],
    ["https://x.com/user/status/123", "twitter"],
    ["https://twitter.com/user", "twitter"],
    ["https://www.tiktok.com/@user1/video/7123", "tiktok"],
    ["https://vm.tiktok.com/ZMabc123/", "tiktok"],
    ["https://example.com/foo", null],
    ["", null],
  ];

  it.each(cases)("%s → %s", (input, expected) => {
    expect(detectPlatform(input)).toBe(expected);
  });
});

describe("detectUrl", () => {
  it("extracts tiktok author + contentType", () => {
    const d = detectUrl("https://www.tiktok.com/@user1/video/7123");
    expect(d?.contentType).toBe("tiktok");
    expect(d?.author).toBe("user1");
  });

  it("keeps an Instagram profile detectable without forcing content type", () => {
    const profile = detectUrl("https://www.instagram.com/creator.name/");
    expect(profile?.platform).toBe("instagram");
    expect(profile?.contentType).toBeNull();
    expect(profile?.author).toBe("creator.name");
  });

  it("detects Instagram stories", () => {
    const story = detectUrl("https://www.instagram.com/stories/creator.name/123/");
    expect(story?.contentType).toBe("story");
    expect(story?.author).toBe("creator.name");
  });
});