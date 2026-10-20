import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useAssetProbe } from "./useAssetProbe";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import { FileInfo } from "../types";

const assetA: FileInfo = { name: "asset-a.png", path: "/test/asset-a.png", ext: "PNG", is_3d: false };
const assetB: FileInfo = { name: "asset-b.svg", path: "/test/asset-b.svg", ext: "SVG", is_3d: false };

describe("useAssetProbe hook", () => {
  it("discards late probe responses from previously selected assets", async () => {
    ApiBridge.clearCache();
    const gateA = Promise.withResolvers<unknown>();
    const gateB = Promise.withResolvers<unknown>();

    const fakeApi = {
      probe_asset: vi.fn((path: string, requestId?: number) => {
        if (path.includes("asset-a")) {
          return gateA.promise.then(() => ({
            ok: true,
            value: {
              kind: "raster",
              resizable: false,
              nativeWidth: 100,
              nativeHeight: 100,
              maxDimension: 8192,
              defaultDimension: 2400,
              requestId,
            },
          }));
        }
        return gateB.promise.then(() => ({
          ok: true,
          value: {
            kind: "vector",
            resizable: true,
            nativeWidth: 500,
            nativeHeight: 500,
            maxDimension: 8192,
            defaultDimension: 2400,
            requestId,
          },
        }));
      }),
    };

    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(({ file }: { file?: FileInfo }) => useAssetProbe(file), {
      initialProps: { file: assetA },
    });

    expect(result.current.isProbing).toBe(true);
    await waitFor(() => {
      expect(fakeApi.probe_asset).toHaveBeenCalledTimes(1);
    });
    // Switch selection to Asset B while Probe A is still pending
    rerender({ file: assetB });
    expect(result.current.probe).toBeNull();
    await waitFor(() => {
      expect(fakeApi.probe_asset).toHaveBeenCalledTimes(2);
    });

    // Asset B probe finishes first
    await act(async () => {
      gateB.resolve(null);
    });

    await waitFor(() => {
      expect(result.current.probe?.kind).toBe("vector");
      expect(result.current.probe?.nativeWidth).toBe(500);
      expect(result.current.isProbing).toBe(false);
    });

    // Asset A probe resolves late: must be ignored and not overwrite Asset B
    await act(async () => {
      gateA.resolve(null);
    });

    expect(result.current.probe?.kind).toBe("vector");
    expect(result.current.probe?.nativeWidth).toBe(500);
  });

  it("discards a late async probe.completed from the previously selected asset", async () => {
    ApiBridge.clearCache();
    const probeA = { kind: "raster", resizable: false, nativeWidth: 100, nativeHeight: 100, maxDimension: 8192, defaultDimension: 2400 };
    const probeB = { kind: "vector", resizable: true, nativeWidth: 500, nativeHeight: 500, maxDimension: 8192, defaultDimension: 2400 };
    const gateA = Promise.withResolvers<unknown>();
    const fakeApi = {
      start_probe: vi.fn((path: string) =>
        path.includes("asset-a")
          ? gateA.promise.then(() => ({ ok: true, operationId: "probe_A", status: "queued" }))
          : Promise.resolve({ ok: true, operationId: "probe_B", status: "queued" })
      ),
      cancel_probe: vi.fn(async () => ({ ok: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(({ file }: { file?: FileInfo }) => useAssetProbe(file), {
      initialProps: { file: assetA },
    });
    await waitFor(() => expect(fakeApi.start_probe).toHaveBeenCalledTimes(1));

    // Switch to asset B while A's start_probe is still in flight
    rerender({ file: assetB });
    await waitFor(() => expect(fakeApi.start_probe).toHaveBeenCalledTimes(2));
    await act(async () => {
      gateA.resolve(null);
    });

    // Late completion for the abandoned operation A must not overwrite B's slot
    act(() => {
      bridgeEvents.emit("probe.completed", { operationId: "probe_A", probe: probeA as never }, { operationId: "probe_A" });
    });
    expect(result.current.probe).toBeNull();
    expect(result.current.isProbing).toBe(true);

    act(() => {
      bridgeEvents.emit("probe.completed", { operationId: "probe_B", probe: probeB as never }, { operationId: "probe_B" });
    });
    expect(result.current.probe?.nativeWidth).toBe(500);
    expect(result.current.isProbing).toBe(false);
    ApiBridge.clearCache();
    delete window.pywebview;
  });

  it("does not hang on 'Probing…' when the backend never becomes available", async () => {
    ApiBridge.clearCache();
    delete window.pywebview;
    const { result } = renderHook(() => useAssetProbe(assetA));
    expect(result.current.isProbing).toBe(true);
    // getApi waits 3s; the hook must resolve to an idle state instead of pinning the badge
    await waitFor(() => expect(result.current.isProbing).toBe(false), { timeout: 6000 });
    ApiBridge.clearCache();
  });

  it("applies a probe.completed that outruns the start_probe promise", async () => {
    ApiBridge.clearCache();
    const probeA = { kind: "raster", resizable: false, nativeWidth: 100, nativeHeight: 100, maxDimension: 8192, defaultDimension: 2400 };
    const gate = Promise.withResolvers<unknown>();
    const fakeApi = {
      start_probe: vi.fn(() => gate.promise),
      cancel_probe: vi.fn(async () => ({ ok: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useAssetProbe(assetA));
    await waitFor(() => expect(fakeApi.start_probe).toHaveBeenCalledTimes(1));

    // The worker finishes before the bridge promise returns to the hook.
    act(() => {
      bridgeEvents.emit("probe.completed", { operationId: "probe_early", probe: probeA as never }, { operationId: "probe_early", terminal: true });
    });
    expect(result.current.probe).toBeNull();

    await act(async () => {
      gate.resolve({ ok: true, operationId: "probe_early", status: "queued" });
    });
    await waitFor(() => expect(result.current.probe?.nativeWidth).toBe(100));
    expect(result.current.isProbing).toBe(false);

    // The buffered result must also disarm the timeout backstop.
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 50));
    });
    expect(result.current.probe?.nativeWidth).toBe(100);
    expect(result.current.isProbing).toBe(false);
    ApiBridge.clearCache();
    delete window.pywebview;
  });
});
