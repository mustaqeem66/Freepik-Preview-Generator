import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { usePreview } from "./usePreview";
import { defaultState } from "./useSettings";
import { ApiBridge } from "../api/bridge";
import { FileInfo, PreviewState } from "../types";

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
      render_preview: (_path: string, _state: PreviewState, requestId: number) =>
        new Promise((resolve) => pending.push({ requestId, resolve })),
      release_preview: releasePreview,
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result, rerender } = renderHook(
      ({ file, state }: { file: FileInfo; state: PreviewState }) => usePreview(file, state),
      { initialProps: { file: fileA, state: baseState() } }
    );

    // Allow the debounce timer (40ms) to fire the first request.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60));
    });
    expect(pending).toHaveLength(1);

    // Supersede with a different active file before the first request resolves.
    rerender({ file: fileB, state: baseState() });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60));
    });
    expect(pending).toHaveLength(2);

    // Newest request resolves first and wins.
    await act(async () => {
      pending[1].resolve({ ok: true, value: { url: "http://x/2.jpg", width: 10, height: 10 }, error: null });
    });
    await waitFor(() => expect(result.current.previewUrl).toBe("http://x/2.jpg"));

    // The stale result arrives afterwards; it must be ignored and its file released.
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

  it("does not request a preview when there is no active file", async () => {
    const fakeApi = {
      render_preview: vi.fn(async () => ({ ok: true, value: null, error: null })),
      release_preview: vi.fn(async () => ({ ok: true, value: true, error: null })),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => usePreview(undefined, baseState()));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60));
    });

    expect(result.current.previewUrl).toBeNull();
    expect(fakeApi.render_preview).not.toHaveBeenCalled();
  });
});
