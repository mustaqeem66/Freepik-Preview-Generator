import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useBatch } from "./useBatch";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { BatchSummary } from "../types";

const complete = (overrides: Partial<BatchSummary> = {}): BatchSummary => ({
  planned: 2,
  processed: 2,
  remaining: 0,
  success: 2,
  failed: 0,
  skipped: 0,
  cancelled: false,
  errors: [],
  duration: 1,
  ...overrides,
});

afterEach(() => vi.restoreAllMocks());

describe("useBatch operation safety", () => {
  it("starts idle", () => {
    const { result } = renderHook(() => useBatch());
    expect(result.current.isProcessing).toBe(false);
  });

  it("rejects an obsolete terminal event after a new run starts", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockResolvedValue({ ok: true, operationId: "batch_new" }),
    } as never);
    const { result } = renderHook(() => useBatch());
    await act(async () => {
      await result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
    });
    expect(result.current.isProcessing).toBe(true);
    act(() => {
      bridgeEvents.emit("batch.finished", complete({ cancelled: true }), { operationId: "batch_old" });
      bridgeEvents.emit("batch.progress", { current: 1, total: 2, message: "new run" }, { operationId: "batch_new" });
    });
    expect(result.current.isProcessing).toBe(true);
    expect(result.current.progress.current).toBe(1);
    act(() => {
      bridgeEvents.emit("batch.finished", complete(), { operationId: "batch_new", terminal: true });
    });
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.batchStatus).toBe("completed");
  });

  it("clamps the indeterminate discovery phase to a zero total", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockResolvedValue({ ok: true, operationId: "batch_new" }),
    } as never);
    const { result } = renderHook(() => useBatch());
    await act(async () => {
      await result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
    });
    act(() => {
      bridgeEvents.emit(
        "batch.progress",
        { current: 7, total: -1, message: "Discovering previews… (7 found)" },
        { operationId: "batch_new" }
      );
    });
    expect(result.current.progress.current).toBe(7);
    expect(result.current.progress.total).toBe(0);
  });

  it("buffers a fast completion delivered before start returns", async () => {
    let resolveStart: ((value: { ok: boolean; operationId: string }) => void) | undefined;
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockReturnValue(new Promise(resolve => { resolveStart = resolve; })),
    } as never);
    const { result } = renderHook(() => useBatch());
    let running!: Promise<void>;
    act(() => {
      running = result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
    });
    await act(async () => { await Promise.resolve(); });
    act(() => {
      bridgeEvents.emit("batch.finished", complete({ cancelled: true }), { operationId: "batch_old" });
      bridgeEvents.emit("batch.finished", complete(), { operationId: "batch_fast" });
    });
    await act(async () => {
      resolveStart?.({ ok: true, operationId: "batch_fast" });
      await running;
    });
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.batchStatus).toBe("completed");
  });

  it("surfaces backend validation errors instead of hanging", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockResolvedValue({ ok: false, error: "Invalid input" }),
    } as never);
    const { result } = renderHook(() => useBatch());
    await act(async () => {
      await result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
    });
    expect(result.current.batchStatus).toBe("failed");
    expect(result.current.batchErrors).toEqual(["Invalid input"]);
  });

  it("fails the UI when a cancelled batch never emits a terminal event", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockResolvedValue({ ok: true, operationId: "batch_c" }),
      cancel_batch: vi.fn().mockResolvedValue({ ok: true }),
    } as never);
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useBatch());
      await act(async () => {
        await result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
      });
      await act(async () => {
        await result.current.cancelBatch();
      });
      expect(result.current.batchStatus).toBe("batch-cancelling");
      expect(result.current.isProcessing).toBe(true);

      // No batch.finished arrives within the deadline — the watchdog must resolve the stuck state
      await act(async () => { await vi.advanceTimersByTimeAsync(121_000); });
      expect(result.current.isProcessing).toBe(false);
      expect(result.current.batchStatus).toBe("failed");
      expect(result.current.progress.message).toMatch(/timed out/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels the deadline when the terminal event does arrive after cancel", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      start_batch: vi.fn().mockResolvedValue({ ok: true, operationId: "batch_c" }),
      cancel_batch: vi.fn().mockResolvedValue({ ok: true }),
    } as never);
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useBatch());
      await act(async () => {
        await result.current.startBatch("source", "output", 2, { sameFolder: false } as never);
      });
      await act(async () => {
        await result.current.cancelBatch();
      });
      act(() => {
        bridgeEvents.emit("batch.finished", complete({ cancelled: true }), { operationId: "batch_c", terminal: true });
      });
      expect(result.current.batchStatus).toBe("cancelled");

      // The watchdog must not fire afterwards and must not overwrite the real outcome
      await act(async () => { await vi.advanceTimersByTimeAsync(121_000); });
      expect(result.current.batchStatus).toBe("cancelled");
    } finally {
      vi.useRealTimers();
    }
  });
});
