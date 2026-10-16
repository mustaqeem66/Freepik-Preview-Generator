import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBatch } from "./useBatch";

describe("useBatch hook", () => {
  it("initializes with default batch progress and idle state", () => {
    const { result } = renderHook(() => useBatch());
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.progress.current).toBe(0);
    expect(result.current.stats).toEqual({ success: 0, failed: 0 });
    expect(result.current.batchErrors).toEqual([]);
  });

  it("updates progress and finishes batch on window events", () => {
    const { result } = renderHook(() => useBatch());

    act(() => {
      window.__onBatchProgress?.(5, 10, "Processing item 5");
    });
    expect(result.current.progress.current).toBe(5);
    expect(result.current.progress.total).toBe(10);
    expect(result.current.progress.message).toBe("Processing item 5");

    act(() => {
      window.__onBatchFinishedSummary?.({
        planned: 10,
        processed: 10,
        remaining: 0,
        success: 9,
        failed: 1,
        skipped: 0,
        cancelled: false,
        errors: ["Failed item 10"],
        duration: 3.2,
      });
    });

    expect(result.current.isProcessing).toBe(false);
    expect(result.current.stats).toEqual({ success: 9, failed: 1 });
    expect(result.current.batchErrors).toEqual(["Failed item 10"]);
  });
});
