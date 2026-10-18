import { useEffect, useRef, useState } from "react";
import { ApiBridge } from "../api/bridge";
import { AssetProbe, FileInfo } from "../types";

/**
 * Lazily probe the selected asset for its export-size capability and native
 * pixel dimensions. Probes are keyed by path so switching files cancels stale
 * results (a slow probe can never overwrite the current asset's capabilities).
 */
export function useAssetProbe(activeFile: FileInfo | undefined) {
  const [probe, setProbe] = useState<AssetProbe | null>(null);
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const requestRef = useRef<number>(0);

  useEffect(() => {
    const current = ++requestRef.current;
    if (!activeFile) {
      setProbe(null);
      setIsProbing(false);
      return;
    }

    let cancelled = false;
    setProbe(null);
    setIsProbing(true);

    (async () => {
      try {
        const api = await ApiBridge.getApi(3000);
        if (!api?.probe_asset) {
          return;
        }
        const res = await api.probe_asset(activeFile.path, current);
        if (cancelled || current !== requestRef.current) return;
        const value = res && "value" in res ? res.value : null;
        if (value && typeof value.requestId === "number" && value.requestId !== current) {
          return;
        }
        setProbe(value ?? null);
      } catch {
        if (!cancelled && current === requestRef.current) {
          setProbe(null);
        }
      } finally {
        if (!cancelled && current === requestRef.current) {
          setIsProbing(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeFile]);

  return { probe, isProbing };
}
