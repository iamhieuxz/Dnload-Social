import { describe, expect, it } from "vitest";
import { sortNodes, type SortableNode } from "./gallery-sort";

/**
 * Regression: sorting folders by `ctime` never changed position after the
 * first download, because a directory's creation time is fixed. Users
 * sorting by time want "which folder did I just download into", which is
 * the directory's mtime.
 */
describe("sortNodes by time", () => {
  const folders: SortableNode[] = [
    //   name  ctime(created)  mtime(last file written)
    { name: "old-profile", is_dir: true, ctime: 100, mtime: 500 },
    { name: "new-profile", is_dir: true, ctime: 900, mtime: 100 },
    { name: "mid-profile", is_dir: true, ctime: 500, mtime: 300 },
  ];

  it("orders folders by mtime (last file received), not ctime", () => {
    const asc = sortNodes(folders, "ctime", "asc").map((n) => n.name);
    expect(asc).toEqual(["new-profile", "mid-profile", "old-profile"]);
  });

  it("reverses cleanly for desc", () => {
    const desc = sortNodes(folders, "ctime", "desc").map((n) => n.name);
    expect(desc).toEqual(["old-profile", "mid-profile", "new-profile"]);
  });

  it("would give the wrong answer with ctime — guards the regression", () => {
    const byCtime = [...folders]
      .sort((a, b) => (a.ctime ?? 0) - (b.ctime ?? 0))
      .map((n) => n.name);
    const bySortHelper = sortNodes(folders, "ctime", "asc").map((n) => n.name);
    expect(byCtime).not.toEqual(bySortHelper);
  });

  it("uses ctime for files", () => {
    const files: SortableNode[] = [
      { name: "b.jpg", is_dir: false, ctime: 10, mtime: 999 },
      { name: "a.jpg", is_dir: false, ctime: 20, mtime: 1 },
    ];
    expect(sortNodes(files, "ctime", "asc").map((n) => n.name)).toEqual(["b.jpg", "a.jpg"]);
  });

  it("breaks timestamp ties by name so order is stable", () => {
    const tied: SortableNode[] = [
      { name: "zebra", is_dir: true, ctime: 1, mtime: 42 },
      { name: "alpha", is_dir: true, ctime: 1, mtime: 42 },
    ];
    expect(sortNodes(tied, "ctime", "asc").map((n) => n.name)).toEqual(["alpha", "zebra"]);
  });

  it("treats missing timestamps as 0 rather than NaN", () => {
    const missing: SortableNode[] = [
      { name: "has-time", is_dir: true, ctime: 5, mtime: 5 },
      { name: "no-time", is_dir: true },
    ];
    expect(sortNodes(missing, "ctime", "asc").map((n) => n.name)).toEqual([
      "no-time",
      "has-time",
    ]);
  });
});

describe("sortNodes by name", () => {
  it("sorts numerically so 2 comes before 10", () => {
    const nodes: SortableNode[] = [
      { name: "item10", is_dir: true },
      { name: "item2", is_dir: true },
      { name: "item1", is_dir: true },
    ];
    expect(sortNodes(nodes, "name", "asc").map((n) => n.name)).toEqual([
      "item1",
      "item2",
      "item10",
    ]);
  });

  it("is case-insensitive", () => {
    const nodes: SortableNode[] = [
      { name: "banana", is_dir: true },
      { name: "Apple", is_dir: true },
    ];
    expect(sortNodes(nodes, "name", "asc").map((n) => n.name)).toEqual(["Apple", "banana"]);
  });

  it("does not mutate the input array", () => {
    const nodes: SortableNode[] = [
      { name: "b", is_dir: true },
      { name: "a", is_dir: true },
    ];
    const before = nodes.map((n) => n.name);
    sortNodes(nodes, "name", "asc");
    expect(nodes.map((n) => n.name)).toEqual(before);
  });
});