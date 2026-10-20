export interface DownloadFilterState {
  q: string;
  platform: string;
  status: string;
  source: string;
  view: "table" | "list";
}

export function parseDownloadFilters(search: string): DownloadFilterState {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const view = params.get("view");
  return {
    q: params.get("q") ?? "",
    platform: params.get("platform") ?? "",
    status: params.get("status") ?? "",
    source: params.get("source") ?? "",
    view: view === "list" ? "list" : "table",
  };
}

export function serializeDownloadFilters(filters: DownloadFilterState): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.status) params.set("status", filters.status);
  if (filters.source) params.set("source", filters.source);
  if (filters.view !== "table") params.set("view", filters.view);
  return params.toString();
}
