import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { BridgeEventMap, BridgeEventMeta } from "../api/bridge";
import type { FileInfo, PreviewHandle, PreviewState, PyWebViewApi } from "../types";

// Backstop for a lost preview.completed/preview.failed envelope. The backend
// bounds every render (worker timeouts), so this only fires when the event
// itself never arrived; it must stay above the backend render budget.
const PREVIEW_OPERATION_TIMEOUT_MS = 120_000;

type BufferedPreviewEvent =
  | { kind: "completed"; payload: BridgeEventMap["preview.completed"]; meta: BridgeEventMeta }
  | { kind: "failed"; payload: BridgeEventMap["preview.failed"]; meta: BridgeEventMeta };

export function usePreview(activeFile: FileInfo | undefined, state: PreviewState) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewSourcePath, setPreviewSourcePath] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<{ width: number; height: number; name: string }>({
    width: 0,
    height: 0,
    name: "",
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  const activeFilePathRef = useRef<string | undefined>(activeFile?.path);
  activeFilePathRef.current = activeFile?.path;
  const requestIdRef = useRef<number>(0);
  const activeOpIdRef = useRef<string | null>(null);
  const ownedHandleRef = useRef<PreviewHandle | null>(null);
  const apiRef = useRef<PyWebViewApi | undefined>(undefined);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A terminal envelope can beat the start_preview promise back to the hook.
  // While that call is in flight there is no operation id to match against, so
  // events are buffered and replayed the moment the id is known.
  const startPendingRef = useRef<boolean>(false);
  const settledRef = useRef<boolean>(false);
  const bufferedRef = useRef<BufferedPreviewEvent[]>([]);
  const replayRef = useRef<((operationId: string) => void) | null>(null);

  const clearWatchdog = () => {
    if (watchdogRef.current !== null) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  };

  const releaseHandle = (handle: PreviewHandle | null): void => {
    const api = apiRef.current;
    if (handle && api?.release_preview) {
      Promise.resolve(api.release_preview(handle.id)).catch(() => {});
    }
  };

  useEffect(() => {
    // Listen for asynchronous preview completion and failure events
    const applyCompleted = (payload: BridgeEventMap["preview.completed"]) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) {
        // Discard superseded preview
        releaseHandle({ id: payload.previewId || payload.url, url: payload.url, requestId: 0 });
        return;
      }
      clearWatchdog();
      settledRef.current = true;
      setIsLoading(false);
      setRenderError(null);
      const newHandle: PreviewHandle = {
        id: payload.previewId || payload.url,
        url: payload.url,
        requestId: requestIdRef.current,
      };
      const previous = ownedHandleRef.current;
      ownedHandleRef.current = newHandle;
      setPreviewUrl(newHandle.url);
      setPreviewSourcePath(activeFilePathRef.current ?? null);
      setPreviewMeta({
        width: payload.width,
        height: payload.height,
        name: activeFile?.name || "",
      });
      if (previous && previous.id !== newHandle.id) {
        releaseHandle(previous);
      }
    };

    const applyFailed = (payload: BridgeEventMap["preview.failed"]) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      clearWatchdog();
      settledRef.current = true;
      setIsLoading(false);
      setRenderError(payload.error || "Preview generation failed");
    };

    const unsubCompleted = bridgeEvents.subscribe("preview.completed", (payload, meta) => {
      if (startPendingRef.current) {
        bufferedRef.current.push({ kind: "completed", payload, meta });
        return;
      }
      applyCompleted(payload);
    });

    const unsubFailed = bridgeEvents.subscribe("preview.failed", (payload, meta) => {
      if (startPendingRef.current) {
        bufferedRef.current.push({ kind: "failed", payload, meta });
        return;
      }
      applyFailed(payload);
    });

    replayRef.current = (operationId: string) => {
      const buffered = bufferedRef.current;
      bufferedRef.current = [];
      for (const entry of buffered) {
        const eventOpId = entry.payload.operationId || entry.meta.operationId;
        if (eventOpId !== operationId) {
          // Belongs to a superseded run: drop it, but free its server buffer.
          if (entry.kind === "completed") {
            releaseHandle({
              id: entry.payload.previewId || entry.payload.url,
              url: entry.payload.url,
              requestId: 0,
            });
          }
          continue;
        }
        if (entry.kind === "completed") applyCompleted(entry.payload);
        else applyFailed(entry.payload);
      }
    };

    return () => {
      unsubCompleted();
      unsubFailed();
      replayRef.current = null;
      releaseHandle(ownedHandleRef.current);
      ownedHandleRef.current = null;
    };
  }, [activeFile?.name]);

  useEffect(() => {
    if (!activeFile) {
      if (apiRef.current?.cancel_preview && activeOpIdRef.current) {
        apiRef.current.cancel_preview(activeOpIdRef.current).catch(() => {});
      }
      activeOpIdRef.current = null;
      releaseHandle(ownedHandleRef.current);
      ownedHandleRef.current = null;
      setPreviewUrl(null);
      setPreviewSourcePath(null);
      setPreviewMeta({ width: 0, height: 0, name: "" });
      setRenderError(null);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    if (ownedHandleRef.current && previewMeta.name !== activeFile.name) {
      releaseHandle(ownedHandleRef.current);
      ownedHandleRef.current = null;
      setPreviewUrl(null);
      setPreviewSourcePath(null);
      setPreviewMeta({ width: 0, height: 0, name: "" });
    }
    setRenderError(null);

    let cancelled = false;
    // Debounce preview request: 120ms to absorb rapid continuous slider dragging and typing
    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const api = await ApiBridge.getApi(3000);
        if (!api) throw new Error("Backend unavailable. Reconnect to render this asset.");
        apiRef.current = api;

        if (api.start_preview) {
          // P0 fix: Non-blocking asynchronous start_preview
          startPendingRef.current = true;
          settledRef.current = false;
          const res = await api.start_preview(activeFile.path, state, currentRequestId);
          startPendingRef.current = false;
          if (cancelled || currentRequestId !== requestIdRef.current) {
            if (res.operationId) api.cancel_preview?.(res.operationId).catch(() => {});
            return;
          }
          if (res.ok && res.operationId) {
            activeOpIdRef.current = res.operationId;
            // Deliver any terminal envelope that outran this promise.
            replayRef.current?.(res.operationId);
            if (settledRef.current) return; // replay already delivered the outcome
            // Watchdog: a lost terminal envelope must not pin "Rendering" forever.
            watchdogRef.current = setTimeout(() => {
              if (activeOpIdRef.current !== res.operationId) return;
              activeOpIdRef.current = null;
              setIsLoading(false);
              setRenderError("Preview generation timed out. Try again or pick another asset.");
            }, PREVIEW_OPERATION_TIMEOUT_MS);
          } else {
            // ok without an operation id is a failure: never pin "Rendering".
            setIsLoading(false);
            setRenderError(res.error || "Preview generation failed. Try again.");
          }
        } else {
          // Fallback to synchronous render_preview if older backend
          const res = await api.render_preview(activeFile.path, state, currentRequestId);
          const value = res && "value" in res ? res.value : null;
          if (cancelled || currentRequestId !== requestIdRef.current) {
            if (value?.url) {
              releaseHandle({
                id: value.previewId || value.url,
                url: value.url,
                requestId: currentRequestId,
              });
            }
            return;
          }
          setIsLoading(false);
          if (value) {
            const newHandle: PreviewHandle = {
              id: value.previewId || value.url,
              url: value.url,
              requestId: currentRequestId,
            };
            const previous = ownedHandleRef.current;
            ownedHandleRef.current = newHandle;
            setPreviewUrl(newHandle.url);
            setPreviewSourcePath(activeFile.path);
            setPreviewMeta({
              width: value.width || 0,
              height: value.height || 0,
              name: activeFile.name,
            });
            setRenderError(null);
            if (previous && previous.id !== newHandle.id) {
              releaseHandle(previous);
            }
          } else if (res && "error" in res && res.error) {
            setRenderError(res.error);
          }
        }
      } catch (err) {
        startPendingRef.current = false;
        if (!cancelled && currentRequestId === requestIdRef.current) {
          setIsLoading(false);
          setRenderError(err instanceof Error ? err.message : "Preview generation failed");
        }
      }
    }, 120);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      startPendingRef.current = false;
      if (watchdogRef.current !== null) {
        clearTimeout(watchdogRef.current);
        watchdogRef.current = null;
      }
      if (apiRef.current?.cancel_preview && activeOpIdRef.current) {
        apiRef.current.cancel_preview(activeOpIdRef.current).catch(() => {});
      }
      // Invalidate the operation gate immediately: a preview.completed for the
      // superseded (old-config) operation must never overwrite the result of
      // the newer request that is still in flight.
      activeOpIdRef.current = null;
    };
  }, [
    activeFile,
    state.text,
    state.position,
    state.opacity,
    state.textColor,
    state.fontPath,
    state.solidColor,
    state.fontScale,
    state.textPosX,
    state.textPosY,
    state.logoPath,
    state.logoScale,
    state.logoOpacity,
    state.logoPosX,
    state.logoPosY,
    state.yaw,
    state.pitch,
    state.modelColor,
    state.hasOutline,
    state.outlineColor,
    state.outlineThickness,
    state.invertTriangles,
    state.autoFrame,
    state.animationContactSheet,
    state.frameMargin,
  ]);

  return { previewUrl, previewSourcePath, previewMeta, isLoading, renderError };
}
