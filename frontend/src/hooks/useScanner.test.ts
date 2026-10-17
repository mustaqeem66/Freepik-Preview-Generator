import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useScanner } from "./useScanner";

describe("useScanner hook", () => {
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
});
