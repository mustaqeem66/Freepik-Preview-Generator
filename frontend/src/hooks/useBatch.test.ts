import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBatch } from "./useBatch";
import { bridgeEvents } from "../api/bridge";

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

  it("updates progress and finishes batch via bridgeEvents typed registry", () => {
    const { result } = renderHook(() => useBatch());

    act(() => {
      bridgeEvents.emit("batch.progress", { current: 3, total: 8, message: "Processing item 3" });
    });
    expect(result.current.progress.current).toBe(3);
    expect(result.current.progress.total).toBe(8);

    act(() => {
      bridgeEvents.emit("batch.finished", {
        planned: 8,
        processed: 8,
        remaining: 0,
        success: 8,
        failed: 0,
        skipped: 0,
        cancelled: false,
        errors: [],
        duration: 1.5,
      });
    });

    expect(result.current.isProcessing).toBe(false);
    expect(result.current.stats).toEqual({ success: 8, failed: 0 });
  });

  it("maps a truncated summary to completed-with-warnings and requires acknowledgement", () => {
    const { result } = renderHook(() => useBatch());

    act(() => {
      bridgeEvents.emit("batch.finished", {
        planned: 100000,
        processed: 1000,
        remaining: 99000,
        success: 1000,
        failed: 0,
        skipped: 0,
        cancelled: false,
        errors: [],
        duration: 12.5,
        status: "completed_with_warnings",
        truncated: true,
        truncationReasons: ["maximum_files"],
        discovered: 100000,
      });
    });

    expect(result.current.batchStatus).toBe("completed-with-warnings");
    expect(result.current.truncationReasons).toEqual(["maximum_files"]);
    expect(result.current.discovered).toBe(100000);
    expect(result.current.requiresTruncationAck).toBe(true);

    act(() => {
      result.current.acknowledgeTruncation();
    });
    expect(result.current.requiresTruncationAck).toBe(false);
  });

  it("maps a cancelled summary to the cancelled state", () => {
    const { result } = renderHook(() => useBatch());

    act(() => {
      bridgeEvents.emit("batch.finished", {
        planned: 10,
        processed: 4,
        remaining: 6,
        success: 4,
        failed: 0,
        skipped: 0,
        cancelled: true,
        errors: [],
        duration: 2.0,
        status: "cancelled",
      });
    });

    expect(result.current.batchStatus).toBe("cancelled");
    expect(result.current.requiresTruncationAck).toBe(false);
  });
});
