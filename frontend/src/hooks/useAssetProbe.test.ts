import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useAssetProbe } from "./useAssetProbe";
import { ApiBridge } from "../api/bridge";
import { FileInfo } from "../types";

describe("useAssetProbe hook", () => {
  it("discards late probe responses from previously selected assets", async () => {
    ApiBridge.clearCache();
    const assetA: FileInfo = { name: "asset-a.png", path: "/test/asset-a.png", ext: "PNG", is_3d: false };
    const assetB: FileInfo = { name: "asset-b.svg", path: "/test/asset-b.svg", ext: "SVG", is_3d: false };
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
});
