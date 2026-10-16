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

  it("updates scan state on window events", () => {
    const { result } = renderHook(() => useScanner());

    act(() => {
      window.__onScanProgress?.("test-scan", 42);
    });
    expect(result.current.scannedCount).toBe(42);

    act(() => {
      window.__onScanFinished?.("test-scan", {
        files: [{ name: "sample.png", path: "/path/sample.png", ext: "PNG", is_3d: false }],
        total: 1,
      });
    });
    expect(result.current.isScanning).toBe(false);
    expect(result.current.fileList).toHaveLength(1);
    expect(result.current.fileList[0]?.name).toBe("sample.png");
  });
});
