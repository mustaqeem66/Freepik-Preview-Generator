import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { FileInfo, PreviewHandle, PreviewState, PyWebViewApi } from "../types";

export function usePreview(activeFile: FileInfo | undefined, state: PreviewState) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
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

  const releaseHandle = (handle: PreviewHandle | null): void => {
    const api = apiRef.current;
    if (handle && api?.release_preview) {
      Promise.resolve(api.release_preview(handle.id)).catch(() => {});
    }
  };

  useEffect(() => {
    // Listen for asynchronous preview completion and failure events
    const unsubCompleted = bridgeEvents.subscribe("preview.completed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) {
        // Discard superseded preview
        releaseHandle({ id: payload.previewId || payload.url, url: payload.url, requestId: 0 });
        return;
      }
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
      setPreviewMeta({
        width: payload.width,
        height: payload.height,
        name: activeFile?.name || "",
      });
      if (previous && previous.id !== newHandle.id) {
        releaseHandle(previous);
      }
    });

    const unsubFailed = bridgeEvents.subscribe("preview.failed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      setIsLoading(false);
      setRenderError(payload.error || "Preview generation failed");
    });

    return () => {
      unsubCompleted();
      unsubFailed();
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
          const res = await api.start_preview(activeFile.path, state, currentRequestId);
          if (cancelled || currentRequestId !== requestIdRef.current) {
            if (res.operationId) api.cancel_preview?.(res.operationId).catch(() => {});
            return;
          }
          if (res.ok && res.operationId) {
            activeOpIdRef.current = res.operationId;
          } else if (res.error) {
            setIsLoading(false);
            setRenderError(res.error);
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
        if (!cancelled && currentRequestId === requestIdRef.current) {
          setIsLoading(false);
          setRenderError(err instanceof Error ? err.message : "Preview generation failed");
        }
      }
    }, 120);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (apiRef.current?.cancel_preview && activeOpIdRef.current) {
        apiRef.current.cancel_preview(activeOpIdRef.current).catch(() => {});
      }
    };
  }, [
    activeFile,
    state.text,
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
    state.hasOutline,
    state.outlineColor,
    state.outlineThickness,
    state.invertTriangles,
  ]);

  return { previewUrl, previewMeta, isLoading, renderError };
}
