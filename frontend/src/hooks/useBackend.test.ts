import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useBackend } from "./useBackend";
import { ApiBridge } from "../api/bridge";

describe("useBackend hook", () => {
  it("transitions to ready upon successful frontend_ready handshake", async () => {
    ApiBridge.clearCache();
    const fakeApi = {
      frontend_ready: async () => ({ ok: true, value: "ready", error: null }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useBackend());

    await waitFor(() => {
      expect(result.current.status).toBe("ready");
    });
    expect(result.current.isConnected).toBe(true);
    expect(result.current.isReady).toBe(true);
  });

  it("transitions to degraded if frontend_ready handshake fails", async () => {
    ApiBridge.clearCache();
    const fakeApi = {
      frontend_ready: async () => ({ ok: false, value: null, error: "Handshake rejected" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useBackend());

    await waitFor(() => {
      expect(result.current.status).toBe("degraded");
    });
    expect(result.current.isConnected).toBe(true);
    expect(result.current.isReady).toBe(false);
  });
});
