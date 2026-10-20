import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { AssetProbe, FileInfo, PyWebViewApi } from "../types";

// Backstop for a lost probe.completed/probe.failed envelope; the backend
// always terminates a probe within its process budget, so this only fires
// when the event itself never arrived.
const PROBE_OPERATION_TIMEOUT_MS = 90_000;

export function useAssetProbe(activeFile: FileInfo | undefined) {
  const [probe, setProbe] = useState<AssetProbe | null>(null);
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const requestRef = useRef<number>(0);
  const activeOpIdRef = useRef<string | null>(null);
  const apiRef = useRef<PyWebViewApi | undefined>(undefined);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubCompleted = bridgeEvents.subscribe("probe.completed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      if (watchdogRef.current !== null) {
        clearTimeout(watchdogRef.current);
        watchdogRef.current = null;
      }
      setProbe(payload.probe ?? null);
      setIsProbing(false);
    });

    const unsubFailed = bridgeEvents.subscribe("probe.failed", (payload) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      if (watchdogRef.current !== null) {
        clearTimeout(watchdogRef.current);
        watchdogRef.current = null;
      }
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
        if (!api || (!api.start_probe && !api.probe_asset)) {
          // No transport to probe with; never leave the UI stuck on "Probing…".
          setProbe(null);
          setIsProbing(false);
          return;
        }
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
            watchdogRef.current = setTimeout(() => {
              if (activeOpIdRef.current === res.operationId) {
                activeOpIdRef.current = null;
                setProbe(null);
                setIsProbing(false);
              }
            }, PROBE_OPERATION_TIMEOUT_MS);
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
      if (watchdogRef.current !== null) {
        clearTimeout(watchdogRef.current);
        watchdogRef.current = null;
      }
      if (apiRef.current?.cancel_probe && activeOpIdRef.current) {
        apiRef.current.cancel_probe(activeOpIdRef.current).catch(() => {});
      }
      // Invalidate the operation gate immediately: a probe.completed for the
      // previous file must not land on the new selection while its start_probe
      // request is still in flight.
      activeOpIdRef.current = null;
    };
  }, [activeFile]);

  return { probe, isProbing };
}
