import type { FileInfo } from "./types";

export function mergeSelectedAssets(previous: FileInfo[], incoming: FileInfo[]): FileInfo[] {
  const paths = new Set(previous.map((item) => item.path));
  const additions: FileInfo[] = [];
  for (const asset of incoming) {
    if (paths.has(asset.path)) continue;
    paths.add(asset.path);
    additions.push(asset);
  }
  return additions.length ? [...previous, ...additions] : previous;
}
