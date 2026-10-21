import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";

type SourceVisual = { path: string; url: string };
type CompareFailure = { path: string; message: string };

/** Source visualizations never enter React as file:// URLs or data URL payloads. */
export function useSourceComparison(path: string | undefined, enabled: boolean) {
  const [image, setImage] = useState<SourceVisual | null>(null);
  const [failure, setFailure] = useState<CompareFailure | null>(null);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const wanted = useRef<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    const current = enabled && path ? path : null;
    wanted.current = current;
    const token = ++generation.current;
    if (!current) {
      setPendingPath(null);
      void ApiBridge.getApi(250).then((api) => {
        if (token !== generation.current) return;
        const request = api?.request_source_comparison?.("");
        return request?.catch(() => {});
      }).catch(() => {});
      return;
    }
    setPendingPath(current);
    setFailure(null);
    const onReady = bridgeEvents.subscribe("comparison.ready", ({ path: incoming, url }) => {
      if (token !== generation.current || incoming !== wanted.current) return;
      setImage({ path: incoming, url });
      setPendingPath(null);
    });
    const onFailed = bridgeEvents.subscribe("comparison.failed", ({ path: incoming }) => {
      if (token !== generation.current || incoming !== wanted.current) return;
      setFailure({ path: incoming, message: "Could not visualize the source file." });
      setPendingPath(null);
    });
    const timer = window.setTimeout(async () => {
      try {
        const api = await ApiBridge.getApi(500);
        if (token !== generation.current) return;
        if (!api?.request_source_comparison) {
          setFailure({ path: current, message: "Source comparison requires the updated desktop backend." });
          setPendingPath(null);
          return;
        }
        const result = await api.request_source_comparison(current);
        if (token !== generation.current) return;
        if (!result.ok) {
          setFailure({ path: current, message: result.error || "Source comparison was rejected." });
          setPendingPath(null);
        } else if (result.value?.[current]) {
          setImage({ path: current, url: result.value[current] });
          setPendingPath(null);
        }
      } catch {
        if (token !== generation.current) return;
        setFailure({ path: current, message: "Desktop renderer is not available." });
        setPendingPath(null);
      }
    }, 100);
    return () => {
      window.clearTimeout(timer);
      onReady();
      onFailed();
      if (wanted.current === current) wanted.current = null;
      generation.current++;
    };
  }, [path, enabled]);

  return {
    sourceUrl: enabled && path && image?.path === path ? image.url : null,
    isLoadingSource: Boolean(enabled && path && pendingPath === path),
    sourceError: enabled && path && failure?.path === path ? failure.message : null,
  };
}
