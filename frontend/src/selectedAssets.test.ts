import { describe, expect, it } from "vitest";
import { mergeSelectedAssets } from "./selectedAssets";
import type { FileInfo } from "./types";
const item = (path: string): FileInfo => ({ name: path.split("/").pop() || "", path, ext: "PNG", is_3d: false });
describe("selected asset collection", () => {
  it("retains order and deduplicates across separate folder picker sessions", () => {
    expect(mergeSelectedAssets([item("/a/a.png")], [item("/a/a.png"), item("/b/b.png"), item("/b/b.png")]))
      .toEqual([item("/a/a.png"), item("/b/b.png")]);
  });
  it("returns original reference for a no-op merge", () => {
    const files = [item("/a/a.png")];
    expect(mergeSelectedAssets(files, [item("/a/a.png")])).toBe(files);
  });
});
