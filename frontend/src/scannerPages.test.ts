import { describe, expect, it, vi } from "vitest";
import { fetchScanPages, ScanTransferSuperseded, SCAN_PAGE_MAX_ITEMS } from "./scannerPages";
import type { FileInfo, PyWebViewApi } from "./types";

const asset = (i: number): FileInfo => ({
  name: `img-${i}.png`, path: `/art/img-${i}.png`, ext: "PNG", is_3d: false,
});

describe("bounded scan page retrieval", () => {
  it("retrieves all assets in bounded pages without losing order", async () => {
    const files = Array.from({ length: 321 }, (_, i) => asset(i));
    const requests: number[] = [];
    const get_scan_page = vi.fn(async (scanId: string, offset: number, limit: number) => {
      expect(scanId).toBe("scan-a");
      expect(limit).toBe(SCAN_PAGE_MAX_ITEMS);
      requests.push(offset);
      const rows = files.slice(offset, offset + limit);
      return { ok: true, error: null, value: {
        scanId, offset, total: files.length, nextOffset: offset + rows.length, files: rows,
      } };
    });
    const progress: number[] = [];
    const received = await fetchScanPages({ get_scan_page } as unknown as PyWebViewApi,
      "scan-a", files.length, () => true, (count) => progress.push(count));
    expect(received).toEqual(files);
    expect(requests).toEqual([0, 128, 256]);
    expect(progress).toEqual([128, 256, 321]);
  });

  it("stops immediately when a newer scan supersedes a slow page", async () => {
    let resolvePage!: (result: unknown) => void;
    const pending = new Promise<unknown>((resolve) => { resolvePage = resolve; });
    const get_scan_page = vi.fn(() => pending);
    let active = true;
    const request = fetchScanPages(
      { get_scan_page } as unknown as PyWebViewApi, "old", 300, () => active);
    active = false;
    resolvePage({ ok: true, value: {
      scanId: "old", offset: 0, total: 300, nextOffset: 1, files: [asset(0)],
    } });
    await expect(request).rejects.toBeInstanceOf(ScanTransferSuperseded);
    expect(get_scan_page).toHaveBeenCalledTimes(1);
  });

  it("rejects incorrect page offsets, scan identifiers and missing data", async () => {
    for (const value of [
      { scanId: "other", offset: 0, total: 129, nextOffset: 1, files: [asset(0)] },
      { scanId: "scan", offset: 25, total: 129, nextOffset: 26, files: [asset(0)] },
      { scanId: "scan", offset: 0, total: 129, nextOffset: 0, files: [] },
    ]) {
      const api = { get_scan_page: vi.fn(async () => ({ ok: true, value })) };
      await expect(fetchScanPages(api as unknown as PyWebViewApi, "scan", 129, () => true))
        .rejects.toThrow("invalid scan result page");
    }
  });

  it("rejects absurd totals and legacy backends without paging", async () => {
    await expect(fetchScanPages(undefined, "scan", 6000, () => true))
      .rejects.toThrow("Invalid paged scan");
    await expect(fetchScanPages({} as PyWebViewApi, "scan", 150, () => true))
      .rejects.toThrow("Update the desktop backend");
  });
});
