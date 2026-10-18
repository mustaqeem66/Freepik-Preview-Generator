import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { computeVirtualWindow, useVirtualList } from "./useVirtualList";

describe("computeVirtualWindow", () => {
  it("renders only the visible slice plus overscan", () => {
    const win = computeVirtualWindow(5000, 34, 0, 200, 6);
    expect(win.totalHeight).toBe(5000 * 34);
    expect(win.start).toBe(0);
    // ceil(200/34) = 6 visible rows, + 6 overscan below.
    expect(win.end).toBe(12);
    expect(win.offsetY).toBe(0);
    expect(win.end - win.start).toBeLessThan(5000);
  });

  it("windows around a deep scroll offset", () => {
    const win = computeVirtualWindow(5000, 34, 3400, 200, 6);
    // floor(3400/34) = 100th row is first visible.
    expect(win.start).toBe(94);
    expect(win.end).toBe(112);
    expect(win.offsetY).toBe(94 * 34);
  });

  it("never exceeds the item count near the end", () => {
    const win = computeVirtualWindow(20, 34, 10_000, 200, 6);
    expect(win.end).toBe(20);
    expect(win.start).toBeLessThanOrEqual(win.end);
  });

  it("returns an empty window for an empty list", () => {
    const win = computeVirtualWindow(0, 34, 0, 200, 6);
    expect(win).toEqual({ start: 0, end: 0, offsetY: 0, totalHeight: 0 });
  });
});

describe("useVirtualList", () => {
  it("returns a bounded window regardless of list size", () => {
    const { result } = renderHook(() => useVirtualList({ count: 100_000, rowHeight: 34, viewportHeight: 200 }));
    const { start, end, totalHeight } = result.current.virtualWindow;
    expect(totalHeight).toBe(100_000 * 34);
    expect(end - start).toBeLessThanOrEqual(13);
  });
});
