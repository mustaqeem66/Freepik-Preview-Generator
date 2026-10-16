import { useState, useEffect, useRef } from "react";
import { PreviewState, FileInfo } from "../types";
import { ApiBridge } from "../api/bridge";

export function usePreview(activeFile: FileInfo | undefined, state: PreviewState) {
  const [previewDataUrl, setPreviewDataUrl] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<{ width: number; height: number; name: string }>({
    width: 0,
    height: 0,
    name: "",
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  const activeFilePathRef = useRef<string | undefined>(activeFile?.path);
  activeFilePathRef.current = activeFile?.path;

  useEffect(() => {
    if (!activeFile) {
      setPreviewDataUrl(null);
      setPreviewMeta({ width: 0, height: 0, name: "" });
      setRenderError(null);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const api = await ApiBridge.getApi(3000);
        if (api) {
          const res = await api.render_preview(activeFile.path, state);
          if (cancelled) return;

          if (res && "value" in res && res.value) {
            setPreviewDataUrl(res.value.dataUrl);
            setPreviewMeta({
              width: res.value.width || 0,
              height: res.value.height || 0,
              name: activeFile.name,
            });
            setRenderError(null);
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

  return { previewDataUrl, previewMeta, isLoading, renderError, setRenderError, setPreviewDataUrl, setPreviewMeta };
}
