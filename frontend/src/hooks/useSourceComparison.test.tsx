import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import { useSourceComparison } from "./useSourceComparison";

afterEach(() => { vi.restoreAllMocks(); });

describe("useSourceComparison", () => {
  it("loads a cached source visualization from the authorized bridge", async () => {
    const run = vi.fn(async (path: string) => ({
      ok: true, value: { [path]: "http://127.0.0.1:5555/source.jpg" }, error: null,
    }));
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({ request_source_comparison: run } as never);
    const { result } = renderHook(() => useSourceComparison("/art/source.png", true));
    await waitFor(() => expect(result.current.sourceUrl).toContain("/source.jpg"));
    expect(run).toHaveBeenCalledWith("/art/source.png");
  });

  it("drops events from the previous asset after selection changes", async () => {
    const run = vi.fn(async () => ({ ok: true, value: {}, error: null }));
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({ request_source_comparison: run } as never);
    const { result, rerender } = renderHook(
      ({ path }) => useSourceComparison(path, true),
      { initialProps: { path: "/art/first.png" } },
    );
    rerender({ path: "/art/second.png" });
    act(() => bridgeEvents.emit("comparison.ready", {
      path: "/art/first.png", url: "http://127.0.0.1:5555/stale.jpg",
    }));
    expect(result.current.sourceUrl).toBeNull();
    act(() => bridgeEvents.emit("comparison.ready", {
      path: "/art/second.png", url: "http://127.0.0.1:5555/current.jpg",
    }));
    expect(result.current.sourceUrl).toContain("current.jpg");
  });

  it("shows actionable compatibility error when running against an older backend", async () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({} as never);
    const { result } = renderHook(() => useSourceComparison("/art/file.png", true));
    await waitFor(() => expect(result.current.sourceError).toMatch(/updated desktop backend/i));
  });
});
