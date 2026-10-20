/**
 * Gallery sort helpers.
 *
 * Folder ordering matters more than it looks: the user comes back to the
 * Gallery to answer "which folder did I just download into?". Sorting
 * folders by creation time answers a different question — when was this
 * folder first created — and never changes afterwards, so a profile
 * downloaded daily would keep the same position forever.
 *
 * A directory's mtime, on the other hand, is bumped every time a file is
 * written into it. So `mtime` is the "most recently received a file"
 * signal, and `ctime` is the "created" signal. Files sort by ctime
 * (they are leaves, no children), folders sort by mtime.
 */

export type SortKey = "name" | "ctime";
export type SortDir = "asc" | "desc";

export interface SortableNode {
  name: string;
  /** Folders sort by mtime; files (is_dir falsy/absent) sort by ctime. */
  is_dir?: boolean;
  mtime?: number;
  ctime?: number;
}

/**
 * Timestamp used to order a node. Folders use mtime (last file written)
 * so "sort by time" surfaces recently-downloaded folders; files use ctime
 * because a leaf file's mtime and ctime are the same event in practice
 * and ctime is what the UI labels "created".
 */
function sortTimestamp(node: SortableNode): number {
  return (node.is_dir ? node.mtime : node.ctime ?? node.mtime) ?? 0;
}

function compareByName(a: SortableNode, b: SortableNode): number {
  return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
}

function compareByTime(a: SortableNode, b: SortableNode): number {
  const diff = sortTimestamp(a) - sortTimestamp(b);
  // Tie-break by name so equal timestamps keep a stable, predictable
  // order instead of shuffling between renders.
  return diff !== 0 ? diff : compareByName(a, b);
}

export function sortNodes<T extends SortableNode>(
  nodes: T[],
  sortKey: SortKey,
  sortDir: SortDir,
): T[] {
  const cmp = sortKey === "name" ? compareByName : compareByTime;
  // `slice()` first — never mutate the caller's array, which comes
  // straight from the react-query cache.
  return [...nodes].sort((a, b) => (sortDir === "asc" ? cmp(a, b) : -cmp(a, b)));
}