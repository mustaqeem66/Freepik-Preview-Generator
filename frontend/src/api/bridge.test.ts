import { describe, it, expect, afterEach, vi } from "vitest";
import { bridgeEvents, BridgeEventMeta } from "./bridge";

describe("bridge typed event hub", () => {
  afterEach(() => {
    bridgeEvents.clear();
    vi.restoreAllMocks();
  });

  it("delivers the full envelope metadata (event/operationId/sequence/payload)", () => {
    const seen: BridgeEventMeta[] = [];
    const off = bridgeEvents.subscribe("scan.progress", ({ scanId, count }, meta) => {
      expect(scanId).toBe("scan-42");
      expect(count).toBe(7);
      seen.push(meta);
    });

    window.__onBridgeEvent?.({
      event: "scan.progress",
      operationId: "scan-42",
      sequence: 3,
      terminal: false,
      payload: { scanId: "scan-42", count: 7 },
    });

    expect(seen).toEqual([{ operationId: "scan-42", sequence: 3, terminal: false }]);
    off();
  });

  it("forwards the terminal flag on the final envelope", () => {
    const seen: BridgeEventMeta[] = [];
    const off = bridgeEvents.subscribe("scan.finished", (_payload, meta) => {
      seen.push(meta);
    });

    window.__onBridgeEvent?.({
      event: "scan.finished",
      operationId: "scan-42",
      sequence: 4,
      terminal: true,
      payload: { scanId: "scan-42", result: { files: [] } as never },
    });

    expect(seen[0]).toEqual({ operationId: "scan-42", sequence: 4, terminal: true });
    off();
  });

  it("propagates operationId from the legacy global fallback", () => {
    const seen: BridgeEventMeta[] = [];
    const off = bridgeEvents.subscribe("scan.finished", (_payload, meta) => {
      seen.push(meta);
    });

    window.__onScanFinished?.("scan-legacy", { files: [], truncated: false } as never);

    expect(seen[0]?.operationId).toBe("scan-legacy");
    expect(seen[0]?.terminal).toBe(true);
    off();
  });

  it("does not install dead batch callback globals", () => {
    const legacy = window as unknown as Record<string, unknown>;
    expect(legacy.__onBatchProgress).toBeUndefined();
    expect(legacy.__onBatchFinishedSummary).toBeUndefined();
    expect(legacy.__onBatchFinished).toBeUndefined();
  });

  it("stops delivery after unsubscribe", () => {
    const listener = vi.fn();
    const off = bridgeEvents.subscribe("batch.progress", listener);
    off();

    window.__onBridgeEvent?.({
      event: "batch.progress",
      payload: { current: 1, total: 2, message: "x" },
    });

    expect(listener).not.toHaveBeenCalled();
  });
});
