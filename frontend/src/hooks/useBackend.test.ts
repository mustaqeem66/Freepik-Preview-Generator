import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useBackend } from "./useBackend";
import { ApiBridge } from "../api/bridge";

describe("useBackend hook", () => {
  beforeEach(() => {
    ApiBridge.clearCache();
  });

  it("transitions to ready upon successful frontend_ready handshake", async () => {
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
    const fakeApi = {
      frontend_ready: async () => ({ ok: false, value: null, error: "Handshake rejected" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useBackend());

    await waitFor(() => {
      expect(result.current.status).toBe("degraded");
    });
    expect(result.current.hasApi).toBe(true);
    expect(result.current.isConnected).toBe(true);
    expect(result.current.isReady).toBe(false);
    expect(typeof result.current.retry).toBe("function");
  });

  it("reports isConnected=false and hasApi=false while connecting without backend", () => {
    window.pywebview = undefined;

    const { result } = renderHook(() => useBackend());
    expect(result.current.status).toBe("connecting");
    expect(result.current.hasApi).toBe(false);
    expect(result.current.isConnected).toBe(false);
    expect(result.current.isReady).toBe(false);
    expect(result.current.isConnecting).toBe(true);
  });

  it("recovers when the backend api is injected after an initial connection failure", async () => {
    let injected = false;
    const fakeApi = {
      frontend_ready: async () => ({ ok: true, value: "ready", error: null }),
    };
    const spy = vi
      .spyOn(ApiBridge, "getApi")
      .mockImplementation(async () => (injected ? (fakeApi as never) : undefined));

    const { result } = renderHook(() => useBackend());
    expect(result.current.status).toBe("connecting");
    await waitFor(() => expect(result.current.status).toBe("disconnected"));

    // Simulate pywebview completing injection and notifying late.
    injected = true;
    await act(async () => {
      window.dispatchEvent(new Event("pywebviewready"));
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.isReady).toBe(true);
    spy.mockRestore();
  });

  it("does not schedule further connection attempts after unmount", async () => {
    window.pywebview = undefined;
    const spy = vi.spyOn(ApiBridge, "getApi").mockResolvedValue(undefined);

    const { unmount } = renderHook(() => useBackend());
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThanOrEqual(1));
    const callsBeforeUnmount = spy.mock.calls.length;

    unmount();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1300));
    });

    expect(spy.mock.calls.length).toBe(callsBeforeUnmount);
    spy.mockRestore();
  });

  it("coalesces overlapping triggers into a single bridge handshake", async () => {
    ApiBridge.clearCache();
    const pending: Array<(value: unknown) => void> = [];
    const fakeApi = {
      frontend_ready: () => new Promise((resolve) => pending.push(resolve)),
    };
    const spy = vi.spyOn(ApiBridge, "getApi").mockResolvedValue(fakeApi as never);

    const { result } = renderHook(() => useBackend());
    await waitFor(() => expect(pending).toHaveLength(1));

    // Firing another trigger while the first check is still in flight must not
    // start a parallel handshake.
    await act(async () => {
      window.dispatchEvent(new Event("pywebviewready"));
    });
    expect(pending).toHaveLength(1);

    await act(async () => {
      pending[0]({ ok: true, value: "ready", error: null });
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    spy.mockRestore();
  });

  it("applies only the newest attempt when checks complete out of order", async () => {
    ApiBridge.clearCache();
    const pending: Array<(value: unknown) => void> = [];
    const fakeApi = {
      frontend_ready: () => new Promise((resolve) => pending.push(resolve)),
    };
    const spy = vi.spyOn(ApiBridge, "getApi").mockResolvedValue(fakeApi as never);

    const { result } = renderHook(() => useBackend());
    await waitFor(() => expect(pending).toHaveLength(1)); // mount attempt (gen 1)

    // Manual retry supersedes the in-flight attempt.
    await act(async () => {
      result.current.retry();
    });
    await waitFor(() => expect(pending).toHaveLength(2)); // gen 2

    // Newest resolves first → ready.
    await act(async () => {
      pending[1]({ ok: true, value: "ready", error: null });
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // The superseded attempt resolves late with a degraded result → ignored.
    await act(async () => {
      pending[0]({ ok: false, value: null, error: "late degraded" });
    });
    expect(result.current.status).toBe("ready");
    spy.mockRestore();
  });

  it("in-flight, pywebviewready and manual retry never let a stale failure clobber ready", async () => {
    // Reproduces the exact interleaving from the P0 audit: a check is running,
    // pywebviewready fires while it is in flight, then the user clicks Retry.
    // pywebviewready must coalesce (no parallel handshake); retry must supersede
    // via the generation guard, so the oldest failure cannot overwrite ready.
    ApiBridge.clearCache();
    const pending: Array<(value: unknown) => void> = [];
    const fakeApi = {
      frontend_ready: () => new Promise((resolve) => pending.push(resolve)),
    };
    const spy = vi.spyOn(ApiBridge, "getApi").mockResolvedValue(fakeApi as never);

    const { result } = renderHook(() => useBackend());
    await waitFor(() => expect(pending).toHaveLength(1)); // gen 1 in flight

    // pywebviewready while gen 1 is in flight → coalesced onto the same attempt.
    await act(async () => {
      window.dispatchEvent(new Event("pywebviewready"));
    });
    expect(pending).toHaveLength(1);

    // Manual retry forces a genuinely new attempt (gen 2).
    await act(async () => {
      result.current.retry();
    });
    await waitFor(() => expect(pending).toHaveLength(2));

    // Newest attempt resolves ready.
    await act(async () => {
      pending[1]({ ok: true, value: "ready", error: null });
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // Oldest attempt resolves late with a failure → must be ignored.
    await act(async () => {
      pending[0]({ ok: false, value: null, error: "stale failure" });
    });
    expect(result.current.status).toBe("ready");
    expect(result.current.isReady).toBe(true);
    spy.mockRestore();
  });

  it("exposes all capabilities when the backend is ready", async () => {
    ApiBridge.clearCache();
    const fakeApi = { frontend_ready: async () => ({ ok: true, value: "ready", error: null }) };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useBackend());
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.capabilities).toEqual({
      canBrowse: true,
      canScan: true,
      canProbe: true,
      canPreview: true,
      canGenerate: true,
      canSaveSettings: true,
      canOpenReport: true,
    });
  });

  it("keeps file and settings capabilities but withholds rendering in degraded mode", async () => {
    ApiBridge.clearCache();
    const fakeApi = { frontend_ready: async () => ({ ok: false, value: null, error: "renderers missing" }) };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useBackend());
    await waitFor(() => expect(result.current.status).toBe("degraded"));
    expect(result.current.capabilities).toEqual({
      canBrowse: true,
      canScan: true,
      canProbe: true,
      canPreview: false,
      canGenerate: false,
      canSaveSettings: true,
      canOpenReport: true,
    });
  });

  it("reports no capabilities while disconnected", () => {
    window.pywebview = undefined;
    const { result } = renderHook(() => useBackend());
    expect(result.current.status).toBe("connecting");
    expect(result.current.capabilities).toEqual({
      canBrowse: false,
      canScan: false,
      canProbe: false,
      canPreview: false,
      canGenerate: false,
      canSaveSettings: false,
      canOpenReport: false,
    });
  });
});
