import { useEffect, useRef, useState } from "react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { BridgeEventMap, BridgeEventMeta } from "../api/bridge";
import type { AssetProbe, FileInfo, PyWebViewApi } from "../types";

// Backstop for a lost probe.completed/probe.failed envelope; the backend
// always terminates a probe within its process budget, so this only fires
// when the event itself never arrived.
const PROBE_OPERATION_TIMEOUT_MS = 90_000;

type BufferedProbeEvent =
  | { kind: "completed"; payload: BridgeEventMap["probe.completed"]; meta: BridgeEventMeta }
  | { kind: "failed"; payload: BridgeEventMap["probe.failed"]; meta: BridgeEventMeta };

export function useAssetProbe(activeFile: FileInfo | undefined) {
  const [probe, setProbe] = useState<AssetProbe | null>(null);
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const requestRef = useRef<number>(0);
  const activeOpIdRef = useRef<string | null>(null);
  const apiRef = useRef<PyWebViewApi | undefined>(undefined);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Terminal envelopes can outrun the start_probe promise; without buffering
  // the result is discarded and the watchdog later reports a false timeout.
  const startPendingRef = useRef<boolean>(false);
  const settledRef = useRef<boolean>(false);
  const bufferedRef = useRef<BufferedProbeEvent[]>([]);
  const replayRef = useRef<((operationId: string) => void) | null>(null);

  const clearWatchdog = () => {
    if (watchdogRef.current !== null) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  };

  useEffect(() => {
    const applyCompleted = (payload: BridgeEventMap["probe.completed"]) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      clearWatchdog();
      settledRef.current = true;
      setProbe(payload.probe ?? null);
      setIsProbing(false);
    };

    const applyFailed = (payload: BridgeEventMap["probe.failed"]) => {
      if (!activeOpIdRef.current || payload.operationId !== activeOpIdRef.current) return;
      clearWatchdog();
      settledRef.current = true;
      setProbe(null);
      setIsProbing(false);
    };

    const unsubCompleted = bridgeEvents.subscribe("probe.completed", (payload, meta) => {
      if (startPendingRef.current) {
        bufferedRef.current.push({ kind: "completed", payload, meta });
        return;
      }
      applyCompleted(payload);
    });

    const unsubFailed = bridgeEvents.subscribe("probe.failed", (payload, meta) => {
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
        if (eventOpId !== operationId) continue; // superseded run
        if (entry.kind === "completed") applyCompleted(entry.payload);
        else applyFailed(entry.payload);
      }
    };

    return () => {
      unsubCompleted();
      unsubFailed();
      replayRef.current = null;
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
          startPendingRef.current = true;
          settledRef.current = false;
          const res = await api.start_probe(activeFile.path, current);
          startPendingRef.current = false;
          if (cancelled || current !== requestRef.current) {
            if (res.operationId) api.cancel_probe?.(res.operationId).catch(() => {});
            return;
          }
          if (res.ok && res.operationId) {
            activeOpIdRef.current = res.operationId;
            replayRef.current?.(res.operationId);
            if (settledRef.current) return; // replay already delivered the outcome
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
        startPendingRef.current = false;
        if (!cancelled && current === requestRef.current) {
          setProbe(null);
          setIsProbing(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      startPendingRef.current = false;
      clearWatchdog();
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
