import { useState, useEffect, useRef } from "react";
import { PreviewState, FileInfo, PreviewHandle, PyWebViewApi } from "../types";
import { ApiBridge } from "../api/bridge";

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
  // The handle this hook currently owns (and is therefore responsible to release).
  const ownedHandleRef = useRef<PreviewHandle | null>(null);
  const apiRef = useRef<PyWebViewApi | undefined>(undefined);

  const releaseHandle = (handle: PreviewHandle | null): void => {
    const api = apiRef.current;
    if (handle && api?.release_preview) {
      // Release by handle id, never by raw URL: the id is the ownership token.
      Promise.resolve(api.release_preview(handle.id)).catch(() => {});
    }
  };

  // On unmount, release the preview we own. Reference counting guarantees a
  // preview shared with another consumer is not deleted underneath it.
  useEffect(
    () => () => {
      releaseHandle(ownedHandleRef.current);
      ownedHandleRef.current = null;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    if (!activeFile) {
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
    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const api = await ApiBridge.getApi(3000);
        if (!api) throw new Error("Backend unavailable. Reconnect to render this asset.");
        if (api) {
          apiRef.current = api;
          const res = await api.render_preview(activeFile.path, state, currentRequestId);
          const value = res && "value" in res ? res.value : null;
          if (cancelled || currentRequestId !== requestIdRef.current) {
            // A superseded request may have already produced a preview file;
            // release the abandoned handle so obsolete frames never accumulate.
            if (value?.url) {
              releaseHandle({
                id: value.previewId || value.url,
                url: value.url,
                requestId: currentRequestId,
              });
            }
            return;
          }
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
              // Release the superseded handle once the new frame is live.
              releaseHandle(previous);
            }
          } else if (res && "error" in res && res.error) {
            setRenderError(res.error);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setRenderError(err instanceof Error ? err.message : "Preview generation failed");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }, 40);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    activeFile,
    state.text,
    state.opacity,
    state.invertTriangles,
    state.solidColor,
    state.textColor,
    state.hasOutline,
    state.outlineColor,
    state.outlineThickness,
    state.fontScale,
    state.textPosX,
    state.textPosY,
    state.logoPath,
    state.logoScale,
    state.logoOpacity,
    state.logoPosX,
    state.logoPosY,
    state.fontPath,
    state.modelColor,
    state.yaw,
    state.pitch,
  ]);

  return { previewUrl, previewMeta, isLoading, renderError, setRenderError, setPreviewUrl, setPreviewMeta };
}
