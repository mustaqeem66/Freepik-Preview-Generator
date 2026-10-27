import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { usePreview } from "./usePreview";
import { defaultState } from "./useSettings";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { FileInfo, PreviewState } from "../types";

const fileA: FileInfo = { name: "a.png", path: "/a.png", ext: "PNG", is_3d: false };
const fileB: FileInfo = { name: "b.png", path: "/b.png", ext: "PNG", is_3d: false };

function baseState(overrides: Partial<PreviewState> = {}): PreviewState {
  return { ...defaultState, ...overrides };
}

interface PendingRequest {
  requestId: number;
  resolve: (value: unknown) => void;
}

describe("usePreview concurrency", () => {
  beforeEach(() => {
    ApiBridge.clearCache();
  });

  afterEach(() => {
    ApiBridge.clearCache();
    delete window.pywebview;
    vi.restoreAllMocks();
  });

  it("suppresses a superseded preview result that resolves late and deletes its file", async () => {
    const pending: PendingRequest[] = [];
    const releasePreview = vi.fn(async () => ({ ok: true, value: true, error: null }));
    const fakeApi = {
      render_preview: (_path: string, _state: PreviewState, requestId: number) => {
        const { promise, resolve } = Promise.withResolvers<unknown>();
        pending.push({ requestId, resolve });
        return promise;
      },
      release_preview: releasePreview,
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(
      ({ file, state }: { file: FileInfo; state: PreviewState }) => usePreview(file, state),
      { initialProps: { file: fileA, state: baseState() } }
    );

    // Wait for the hook debounce timer (120ms) to trigger render_preview
    await waitFor(() => expect(pending).toHaveLength(1));

    // Supersede with a different active file before the first request resolves
    rerender({ file: fileB, state: baseState() });
    await waitFor(() => expect(pending).toHaveLength(2));

    // Newest request resolves first and wins
    await act(async () => {
      pending[1].resolve({ ok: true, value: { url: "http://x/2.jpg", width: 10, height: 10 }, error: null });
    });
    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/2.jpg"));

    // The stale result arrives afterwards; it must be ignored and its file released
    await act(async () => {
      pending[0].resolve({ ok: true, value: { url: "http://x/1.jpg", width: 10, height: 10 }, error: null });
    });
    expect(result.current.previewUrl).toBe("http://x/2.jpg");
    expect(releasePreview).toHaveBeenCalledWith("http://x/1.jpg");
  });

  it("deletes the previous preview file once a newer preview is published", async () => {
    const releasePreview = vi.fn(async () => ({ ok: true, value: true, error: null }));
    let counter = 0;
    const fakeApi = {
      render_preview: async () => ({
        ok: true,
        value: { url: `http://x/${++counter}.jpg`, width: 10, height: 10 },
        error: null,
      }),
      release_preview: releasePreview,
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(fileA, state),
      { initialProps: { state: baseState({ text: "one" }) } }
    );

    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/1.jpg"));

    rerender({ state: baseState({ text: "two" }) });
    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/2.jpg"));
    await waitFor(() => expect(releasePreview).toHaveBeenCalledWith("http://x/1.jpg"));
  });

  it("releases superseded previews by handle id when the backend provides one", async () => {
    const releasePreview = vi.fn(async () => ({ ok: true, value: true, error: null }));
    let counter = 0;
    const fakeApi = {
      render_preview: async () => ({
        ok: true,
        value: { url: `http://x/${++counter}.jpg`, previewId: `preview_00000${counter}`, width: 10, height: 10 },
        error: null,
      }),
      release_preview: releasePreview,
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(fileA, state),
      { initialProps: { state: baseState({ text: "one" }) } }
    );

    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/1.jpg"));
    rerender({ state: baseState({ text: "two" }) });
    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/2.jpg"));
    // Released by the opaque handle id, not the raw URL.
    await waitFor(() => expect(releasePreview).toHaveBeenCalledWith("preview_000001"));
  });

  it("regenerates the current 3D preview when only the untextured model color changes", async () => {
    const startPreview = vi.fn(async (_path: string, _state: PreviewState) => ({ ok: true, operationId: "preview-color", status: "queued" }));
    const cancelPreview = vi.fn(async () => ({ ok: true }));
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: { start_preview: startPreview, cancel_preview: cancelPreview } };
    const mesh: FileInfo = { name: "model.stl", path: "/model.stl", ext: "STL", is_3d: true };
    const { rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(mesh, state),
      { initialProps: { state: baseState({ modelColor: "#7882A0" }) } }
    );
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    rerender({ state: baseState({ modelColor: "#FF0000" }) });
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(2));
    expect(startPreview.mock.calls[1][1]).toMatchObject({ modelColor: "#FF0000" });
  });

  it("requests a fresh preview for a contact-sheet setting change", async () => {
    const startPreview = vi.fn(async (_path: string, _config: PreviewState) =>
      ({ ok: true, operationId: "contacts", status: "queued" }));
    const cancelPreview = vi.fn(async () => ({ ok: true }));
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: { start_preview: startPreview, cancel_preview: cancelPreview } };
    const asset = { ...fileA, name: "sample.gif", path: "/sample.gif", ext: "GIF" };
    const { rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(asset, state),
      { initialProps: { state: baseState({ animationContactSheet: false }) } }
    );
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    rerender({ state: baseState({ animationContactSheet: true }) });
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(2));
    expect(startPreview.mock.calls[1][1]).toMatchObject({ animationContactSheet: true });
  });

  it("regenerates when only the placement preset changes", async () => {
    const startPreview = vi.fn(async (_path: string, _state: PreviewState) =>
      ({ ok: true, operationId: "position-preview", status: "queued" }));
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: { start_preview: startPreview, cancel_preview: vi.fn(async () => ({ ok: true })) } };
    const { rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(fileA, state),
      { initialProps: { state: baseState({ position: "custom" }) } }
    );
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    rerender({ state: baseState({ position: "center" }) });
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(2));
    expect(startPreview.mock.calls[1][1].position).toBe("center");
  });

  it("regenerates live preview when framing changes without another slider update", async () => {
    const startPreview = vi.fn(async (_path: string, _config: PreviewState) =>
      ({ ok: true, operationId: "framed", status: "queued" }));
    const cancelPreview = vi.fn(async () => ({ ok: true }));
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: { start_preview: startPreview, cancel_preview: cancelPreview } };
    const { rerender } = renderHook(
      ({ state }: { state: PreviewState }) => usePreview(fileA, state),
      { initialProps: { state: baseState({ autoFrame: false, frameMargin: 8 }) } }
    );
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    rerender({ state: baseState({ autoFrame: true, frameMargin: 8 }) });
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(2));
    expect(startPreview.mock.calls[1][1]).toMatchObject({ autoFrame: true });
    rerender({ state: baseState({ autoFrame: true, frameMargin: 12 }) });
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(3));
    expect(startPreview.mock.calls[2][1]).toMatchObject({ frameMargin: 12 });
  });

  it("does not request a preview when there is no active file", async () => {
    const fakeApi = {
      render_preview: vi.fn(async () => ({ ok: true, value: null, error: null })),
      release_preview: vi.fn(async () => ({ ok: true, value: true, error: null })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => usePreview(undefined, baseState()));
    await new Promise<void>((resolve) => setTimeout(resolve, 150));

    expect(result.current.previewUrl).toBeNull();
    expect(fakeApi.render_preview).not.toHaveBeenCalled();
  });

  it("discards a completed envelope for a superseded operation id", async () => {
    const fakeApi = {
      start_preview: vi.fn(async (path: string) => ({
        ok: true,
        operationId: path === "/a.png" ? "preview_1" : "preview_2",
        status: "queued",
      })),
      cancel_preview: vi.fn(async () => ({ ok: true })),
      release_preview: vi.fn(async () => ({ ok: true, value: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    vi.useFakeTimers();
    try {
      const { result, rerender } = renderHook(
        ({ file }: { file: FileInfo }) => usePreview(file, baseState()),
        { initialProps: { file: fileA } }
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      rerender({ file: fileB });
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });

      // Stale completion for file A's operation must be ignored
      act(() => {
        bridgeEvents.emit(
          "preview.completed",
          { operationId: "preview_1", url: "http://x/1.jpg", previewId: "p1", width: 10, height: 10 },
          { operationId: "preview_1" }
        );
      });
      expect(result.current.previewUrl).toBeNull();

      act(() => {
        bridgeEvents.emit(
          "preview.completed",
          { operationId: "preview_2", url: "http://x/2.jpg", previewId: "p2", width: 10, height: 10 },
          { operationId: "preview_2" }
        );
      });
      expect(result.current.previewUrl).toBe("http://x/2.jpg");
      expect(result.current.isLoading).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops 'Rendering' when no terminal preview envelope ever arrives", async () => {
    const fakeApi = {
      start_preview: vi.fn(async () => ({ ok: true, operationId: "preview_w", status: "queued" })),
      cancel_preview: vi.fn(async () => ({ ok: true })),
      release_preview: vi.fn(async () => ({ ok: true, value: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => usePreview(fileA, baseState()));
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(result.current.isLoading).toBe(true);

      // Watchdog deadline (120s) fires because the backend envelope was lost
      await act(async () => { await vi.advanceTimersByTimeAsync(121_000); });
      expect(result.current.isLoading).toBe(false);
      expect(result.current.renderError).toMatch(/timed out/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it("applies a terminal envelope that outruns the start_preview promise", async () => {
    const gate = Promise.withResolvers<unknown>();
    const fakeApi = {
      start_preview: vi.fn(() => gate.promise),
      cancel_preview: vi.fn(async () => ({ ok: true })),
      release_preview: vi.fn(async () => ({ ok: true, value: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => usePreview(fileA, baseState()));
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(fakeApi.start_preview).toHaveBeenCalledTimes(1);

      // The worker publishes before the bridge promise returns to the hook.
      act(() => {
        bridgeEvents.emit(
          "preview.completed",
          { operationId: "preview_early", url: "http://x/e.jpg", previewId: "pe", width: 40, height: 30 },
          { operationId: "preview_early", terminal: true }
        );
      });
      expect(result.current.previewUrl).toBeNull();

      await act(async () => {
        gate.resolve({ ok: true, operationId: "preview_early", status: "queued" });
      });
      expect(result.current.previewUrl).toBe("http://x/e.jpg");
      expect(result.current.isLoading).toBe(false);
      expect(result.current.renderError).toBeNull();

      // Buffering the early event must also cancel the false-timeout watchdog.
      await act(async () => { await vi.advanceTimersByTimeAsync(121_000); });
      expect(result.current.renderError).toBeNull();
      expect(result.current.previewUrl).toBe("http://x/e.jpg");
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports a failure instead of pinning Rendering when start gives no operation id", async () => {
    const fakeApi = {
      start_preview: vi.fn(async () => ({ ok: true, status: "queued" })),
      cancel_preview: vi.fn(async () => ({ ok: true })),
      release_preview: vi.fn(async () => ({ ok: true, value: true })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => usePreview(fileA, baseState()));
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(result.current.isLoading).toBe(false);
      expect(result.current.renderError).toMatch(/failed/i);
    } finally {
      vi.useRealTimers();
    }
  });
});
