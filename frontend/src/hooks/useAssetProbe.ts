import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { AssetProbe, FileInfo, PyWebViewApi } from "../types";

export function useAssetProbe(activeFile: FileInfo | undefined) {
  const [probe, setProbe] = useState<AssetProbe | null>(null);
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const requestRef = useRef<number>(0);
  const activeOpIdRef = useRef<string | null>(null);
  const apiRef = useRef<PyWebViewApi | undefined>(undefined);

  useEffect(() => {
    const unsubCompleted = bridgeEvents.subscribe("probe.completed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      setProbe(payload.probe ?? null);
      setIsProbing(false);
    });

    const unsubFailed = bridgeEvents.subscribe("probe.failed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      setProbe(null);
      setIsProbing(false);
    });

    return () => {
      unsubCompleted();
      unsubFailed();
    };
  }, []);

  useEffect(() => {
    const current = ++requestRef.current;
    if (!activeFile) {
      if (apiRef.current?.cancel_probe && activeOpIdRef.current) {
        apiRef.current.cancel_probe(activeOpIdRef.current).catch(() => {});
      }
      activeOpIdRef.current = null;
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
        if (!api) return;
        apiRef.current = api;

        if (api.start_probe) {
          // P0 fix: Non-blocking asynchronous start_probe
          const res = await api.start_probe(activeFile.path, current);
          if (cancelled || current !== requestRef.current) {
            if (res.operationId) api.cancel_probe?.(res.operationId).catch(() => {});
            return;
          }
          if (res.ok && res.operationId) {
            activeOpIdRef.current = res.operationId;
          } else {
            setIsProbing(false);
          }
        } else if (api.probe_asset) {
          // Fallback to synchronous probe_asset
          const res = await api.probe_asset(activeFile.path, current);
          if (cancelled || current !== requestRef.current) return;
          const value = res && "value" in res ? res.value : null;
          setProbe(value ?? null);
          setIsProbing(false);
        }
      } catch {
        if (!cancelled && current === requestRef.current) {
          setProbe(null);
          setIsProbing(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (apiRef.current?.cancel_probe && activeOpIdRef.current) {
        apiRef.current.cancel_probe(activeOpIdRef.current).catch(() => {});
      }
    };
  }, [activeFile]);

  return { probe, isProbing };
}
