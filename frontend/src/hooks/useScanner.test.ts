import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
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
      await result.current.scanFolder("/path/two");
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
});
