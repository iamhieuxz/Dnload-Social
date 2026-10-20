import { describe, expect, it } from "vitest";
import { parseDownloadFilters, serializeDownloadFilters } from "./download-filters";

describe("download filters round-trip", () => {
  const filters = {
    q: " creator ",
    platform: "instagram",
    status: "failed",
    source: "database",
    view: "list" as const,
  };

  it("serializes in a stable order", () => {
    expect(serializeDownloadFilters(filters)).toBe(
      "q=creator&platform=instagram&status=failed&source=database&view=list",
    );
  });

  it("parses back and trims the query", () => {
    const encoded = serializeDownloadFilters(filters);
    expect(parseDownloadFilters(`?${encoded}`)).toEqual({ ...filters, q: "creator" });
  });

  it("defaults to table view", () => {
    expect(parseDownloadFilters("").view).toBe("table");
  });
});