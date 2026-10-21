import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useScanner } from "./useScanner";
import { ApiBridge } from "../api/bridge";

describe("useScanner hook", () => {
  beforeEach(() => {
    ApiBridge.clearCache();
  });

  afterEach(() => {
    ApiBridge.clearCache();
    delete window.pywebview;
  });

  it("initializes with empty file list and idle state", () => {
    const { result } = renderHook(() => useScanner());
    expect(result.current.fileList).toEqual([]);
    expect(result.current.isScanning).toBe(false);
    expect(result.current.scannedCount).toBe(0);
    expect(result.current.scanError).toBeNull();
  });

  it("filters out stale or mismatched scanId progress and completion events", async () => {
    // Mock ApiBridge start_scan
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "active-scan-123" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useScanner());

    await act(async () => {
      await result.current.scanFolder("/path/to/folder");
    });
    expect(result.current.isScanning).toBe(true);

    // Stale/unrelated scan event should be ignored
    act(() => {
      window.__onScanProgress?.("stale-scan-999", 50);
    });
    expect(result.current.scannedCount).toBe(0);

    act(() => {
      window.__onScanFinished?.("stale-scan-999", {
        files: [{ name: "wrong.png", path: "/path/wrong.png", ext: "PNG", is_3d: false }],
        total: 1,
      });
    });
    expect(result.current.isScanning).toBe(true);
    expect(result.current.fileList).toHaveLength(0);

    // Correct active scan events should be accepted
    act(() => {
      window.__onScanProgress?.("active-scan-123", 50);
    });
    expect(result.current.scannedCount).toBe(50);

    act(() => {
      window.__onScanFinished?.("active-scan-123", {
        files: [{ name: "correct.png", path: "/path/correct.png", ext: "PNG", is_3d: false }],
        total: 1,
      });
    });
    expect(result.current.isScanning).toBe(false);
    expect(result.current.fileList).toHaveLength(1);
    expect(result.current.fileList[0]?.name).toBe("correct.png");
  });

  it("preserves the previous file list when a scan is cancelled", async () => {
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "scan-a" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useScanner());

    // Establish a completed baseline result.
    await act(async () => {
      await result.current.scanFolder("/path/one");
    });
    act(() => {
      window.__onScanFinished?.("scan-a", {
        files: [{ name: "keep.png", path: "/path/keep.png", ext: "PNG", is_3d: false }],
        total: 1,
        status: "completed",
      });
    });
    expect(result.current.fileList).toHaveLength(1);
    expect(result.current.scanStatus).toBe("completed");

    // A subsequent cancelled scan must not wipe the existing list.
    fakeApi.start_scan = async () => ({ ok: true, scanId: "scan-b" });
    await act(async () => {
      await result.current.scanFolder("/path/one");
    });
    act(() => {
      window.__onScanFinished?.("scan-b", { files: [], total: 0, status: "cancelled" });
    });

    expect(result.current.scanStatus).toBe("scan-cancelled");
    expect(result.current.isScanning).toBe(false);
    expect(result.current.fileList).toHaveLength(1);
    expect(result.current.fileList[0]?.name).toBe("keep.png");
  });

  it("marks the scan cancelled when cancelScan is invoked", async () => {
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "scan-c" }),
      cancel_scan: async () => undefined,
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useScanner());
    await act(async () => {
      await result.current.scanFolder("/path/three");
    });

    await act(async () => {
      await result.current.cancelScan();
    });

    expect(result.current.scanStatus).toBe("scan-cancelling");
    expect(result.current.isScanning).toBe(true);
    act(() => {
      window.__onScanFinished?.("scan-c", { files: [], total: 0, status: "cancelled" });
    });
    expect(result.current.scanStatus).toBe("scan-cancelled");
    expect(result.current.isScanning).toBe(false);
  });

  it("adopts a truncated scan but flags it as scan-truncated", async () => {
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "scan-t" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useScanner());
    await act(async () => {
      await result.current.scanFolder("/path/truncated");
    });

    act(() => {
      window.__onScanFinished?.("scan-t", {
        files: [{ name: "a.png", path: "/p/a.png", ext: "PNG", is_3d: false }],
        total: 1,
        status: "truncated",
        truncated: true,
        truncationReasons: ["maximum_files"],
        discovered: 5000,
      });
    });

    // A truncated scan is visually distinct from a complete one and adopts the
    // partial result so the user can still work with what was found.
    expect(result.current.scanStatus).toBe("scan-truncated");
    expect(result.current.scanTruncated).toBe(true);
    expect(result.current.scanTruncationReasons).toEqual(["maximum_files"]);
    expect(result.current.scanDiscovered).toBe(5000);
    expect(result.current.isScanning).toBe(false);
    expect(result.current.fileList).toHaveLength(1);
  });
  it("clears stale assets before scanning a different folder", async () => {
    let scanId = "A";
    const fakeApi = { start_scan: async () => ({ ok: true, scanId }) };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };
    const { result } = renderHook(() => useScanner());
    await act(async () => { await result.current.scanFolder("/folder/a"); });
    act(() => {
      window.__onScanFinished?.("A", {
        files: [{ name: "a.png", path: "/folder/a/a.png", ext: "PNG", is_3d: false }],
        total: 1, status: "completed",
      });
    });
    expect(result.current.fileList).toHaveLength(1);
    scanId = "B";
    await act(async () => { await result.current.scanFolder("/folder/b"); });
    expect(result.current.fileList).toEqual([]);
    expect(result.current.isScanning).toBe(true);
    act(() => { window.__onScanFinished?.("B", { files: [], total: 0, status: "cancelled" }); });
    expect(result.current.fileList).toEqual([]);
    expect(result.current.scanStatus).toBe("scan-cancelled");
  });

  it("sends a scan-specific cancellation if Cancel occurs before start resolves", async () => {
    let finishStart!: (response: { ok: boolean; scanId: string }) => void;
    const deferred = new Promise<{ ok: boolean; scanId: string }>((resolve) => { finishStart = resolve; });
    const cancel_scan = vi.fn(async () => ({ ok: true, cancelled: true }));
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: { start_scan: () => deferred, cancel_scan } };
    const { result } = renderHook(() => useScanner());
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.scanFolder("/slow");
      await Promise.resolve();
    });
    await act(async () => { await result.current.cancelScan(); });
    expect(result.current.scanStatus).toBe("scan-cancelling");
    expect(cancel_scan).not.toHaveBeenCalled();
    await act(async () => {
      finishStart({ ok: true, scanId: "slow-id" });
      await pending;
    });
    await waitFor(() => expect(cancel_scan).toHaveBeenCalledWith("slow-id"));
    expect(result.current.scanStatus).toBe("scan-cancelling");
    act(() => {
      window.__onScanFinished?.("slow-id", { files: [], total: 0, status: "cancelled" });
    });
    expect(result.current.scanStatus).toBe("scan-cancelled");
  });
  it("loads 320 scanned assets from bounded pages before replacing the library", async () => {
    const all = Array.from({ length: 320 }, (_, i) => ({
      name: `sample-${i}.png`, path: `/root/sample-${i}.png`, ext: "PNG", is_3d: false,
    }));
    const offsets: number[] = [];
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "paged-a" }),
      get_scan_page: vi.fn(async (scanId: string, offset: number, limit: number) => {
        expect(scanId).toBe("paged-a");
        expect(limit).toBe(128);
        offsets.push(offset);
        const rows = all.slice(offset, offset + limit);
        return { ok: true, error: null, value: {
          scanId, offset, total: all.length,
          files: rows, nextOffset: offset + rows.length,
        } };
      }),
    };
    // @ts-expect-error bridge test stub
    window.pywebview = { api: fakeApi };
    const { result } = renderHook(() => useScanner());
    await act(async () => { await result.current.scanFolder("/root"); });
    act(() => {
      window.__onScanFinished?.("paged-a", {
        files: [], total: 320, status: "completed", paged: { total: 320, pageSize: 128 },
      });
    });
    expect(result.current.isScanning).toBe(true);
    expect(result.current.fileList).toEqual([]);
    await waitFor(() => expect(result.current.isScanning).toBe(false));
    expect(result.current.scanStatus).toBe("completed");
    expect(result.current.fileList).toEqual(all);
    expect(offsets).toEqual([0, 128, 256]);
  });

  it("does not adopt an old paged scan after a new folder starts", async () => {
    let resolvePage!: (response: unknown) => void;
    const pending = new Promise<unknown>((resolve) => { resolvePage = resolve; });
    let scanId = "old-paged";
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId }),
      cancel_scan: vi.fn(async () => ({ ok: true, cancelled: true })),
      get_scan_page: vi.fn(() => pending),
    };
    // @ts-expect-error bridge test stub
    window.pywebview = { api: fakeApi };
    const { result } = renderHook(() => useScanner());
    await act(async () => { await result.current.scanFolder("/one"); });
    act(() => {
      window.__onScanFinished?.("old-paged", {
        files: [], total: 200, status: "completed",
        paged: { total: 200, pageSize: 128 },
      });
    });
    await waitFor(() => expect(fakeApi.get_scan_page).toHaveBeenCalledTimes(1));
    scanId = "new-scan";
    await act(async () => { await result.current.scanFolder("/two"); });
    act(() => {
      window.__onScanFinished?.("new-scan", {
        files: [{ name: "new.png", path: "/two/new.png", ext: "PNG", is_3d: false }],
        total: 1, status: "completed",
      });
    });
    await act(async () => {
      resolvePage({ ok: true, error: null, value: {
        scanId: "old-paged", offset: 0, total: 200, nextOffset: 1,
        files: [{ name: "old.png", path: "/one/old.png", ext: "PNG", is_3d: false }],
      } });
      await Promise.resolve();
    });
    expect(result.current.fileList.map((file) => file.name)).toEqual(["new.png"]);
    expect(result.current.scanStatus).toBe("completed");
  });

  it("fails visibly without adopting partial rows if page transfer breaks", async () => {
    const fakeApi = {
      start_scan: async () => ({ ok: true, scanId: "broken" }),
      get_scan_page: vi.fn(async () => ({ ok: false, value: null, error: "SCAN_RESULT_EXPIRED" })),
    };
    // @ts-expect-error bridge test stub
    window.pywebview = { api: fakeApi };
    const { result } = renderHook(() => useScanner());
    await act(async () => { await result.current.scanFolder("/broken"); });
    act(() => {
      window.__onScanFinished?.("broken", {
        files: [], total: 300, status: "completed",
        paged: { total: 300, pageSize: 128 },
      });
    });
    await waitFor(() => expect(result.current.isScanning).toBe(false));
    expect(result.current.fileList).toHaveLength(0);
    expect(result.current.scanStatus).toBe("idle");
    expect(result.current.scanError).toContain("SCAN_RESULT_EXPIRED");
  });

  it("accepts paged results that finish before start_scan resolves", async () => {
    let startResolve!: (response: { ok: boolean; scanId: string }) => void;
    const pending = new Promise<{ ok: boolean; scanId: string }>((resolve) => {
      startResolve = resolve;
    });
    const rows = Array.from({ length: 130 }, (_, i) => ({
      name: `f-${i}.png`, path: `/early/f-${i}.png`, ext: "PNG", is_3d: false,
    }));
    const fakeApi = {
      start_scan: () => pending,
      get_scan_page: vi.fn(async (scanId: string, offset: number, limit: number) => {
        const slice = rows.slice(offset, offset + limit);
        return { ok: true, error: null, value: {
          scanId, offset, total: rows.length, nextOffset: offset + slice.length, files: slice,
        } };
      }),
    };
    // @ts-expect-error bridge test stub
    window.pywebview = { api: fakeApi };
    const { result } = renderHook(() => useScanner());
    let request!: Promise<void>;
    await act(async () => { request = result.current.scanFolder("/early"); });
    act(() => {
      window.__onScanFinished?.("early-scan", {
        files: [], total: 130, status: "completed",
        paged: { total: 130, pageSize: 128 },
      });
    });
    await act(async () => {
      startResolve({ ok: true, scanId: "early-scan" });
      await request;
    });
    await waitFor(() => expect(result.current.fileList).toHaveLength(130));
    expect(result.current.scanStatus).toBe("completed");
  });

});
