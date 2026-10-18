import { useState, useEffect, useCallback, useRef } from "react";
import { ApiBridge } from "../api/bridge";

export type BackendStatus = "connecting" | "connected" | "ready" | "degraded" | "disconnected";

/**
 * Explicit, per-action capability model. Controls should gate on the capability
 * they actually need rather than on one broad "connected" boolean, so a degraded
 * backend (bridge present, handshake not ready) can still browse and scan while
 * render/generate actions stay disabled.
 */
export interface BackendCapabilities {
  canBrowse: boolean;
  canScan: boolean;
  canProbe: boolean;
  canPreview: boolean;
  canGenerate: boolean;
  canSaveSettings: boolean;
  canOpenReport: boolean;
}

export interface BackendState {
  status: BackendStatus;
  isConnected: boolean;
  hasApi: boolean;
  isReady: boolean;
  isConnecting: boolean;
  capabilities: BackendCapabilities;
  retry: () => void;
}

interface CheckOutcome {
  /** The handshake ultimately reported the backend as ready. */
  success: boolean;
  /** This attempt was still the newest when it completed (not superseded). */
  accepted: boolean;
}

const MAX_RETRIES = 5;
const RETRY_DELAY_BASE = 1000; // 1 second base delay

export function useBackend(): BackendState {
  const [status, setStatus] = useState<BackendStatus>("connecting");
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  // Monotonic attempt generation: only the newest attempt may mutate status, so
  // overlapping triggers (mount / pywebviewready / manual retry / scheduled
  // retry) can never let an older result clobber a newer one.
  const attemptGenerationRef = useRef(0);
  const inFlightRef = useRef<Promise<CheckOutcome> | null>(null);

  const checkBackend = useCallback((coalesce = true): Promise<CheckOutcome> => {
    // Non-forced triggers while a check is already in flight share that check
    // instead of issuing a parallel bridge handshake.
    if (coalesce && inFlightRef.current) {
      return inFlightRef.current;
    }

    const generation = ++attemptGenerationRef.current;
    const isLatest = () => mountedRef.current && generation === attemptGenerationRef.current;

    let task: Promise<CheckOutcome>;
    task = (async (): Promise<CheckOutcome> => {
      const api = await ApiBridge.getApi(4000);
      if (!isLatest()) return { success: false, accepted: false };
      if (!api) {
        setStatus("disconnected");
        return { success: false, accepted: true };
      }

      try {
        if (api.frontend_ready) {
          const res = await api.frontend_ready();
          if (!isLatest()) return { success: false, accepted: false };
          if (res && "ok" in res && res.ok === false) {
            setStatus("degraded");
            return { success: false, accepted: true };
          }
        }
        if (isLatest()) {
          setStatus("ready");
          retryCountRef.current = 0;
        }
        return { success: true, accepted: true };
      } catch (err) {
        console.warn("frontend_ready handshake warning:", err);
        if (isLatest()) {
          setStatus("degraded");
        }
        return { success: false, accepted: isLatest() };
      }
    })().finally(() => {
      if (inFlightRef.current === task) {
        inFlightRef.current = null;
      }
    });

    inFlightRef.current = task;
    return task;
  }, []);

  const scheduleRetry = useCallback(() => {
    // A retry is already pending; do not stack timers or double-count attempts.
    if (retryTimerRef.current !== null) return;
    if (retryCountRef.current >= MAX_RETRIES) {
      if (mountedRef.current) {
        setStatus("disconnected");
      }
      return;
    }
    retryCountRef.current += 1;
    const baseDelay = RETRY_DELAY_BASE * Math.pow(2, retryCountRef.current - 1);
    // Bounded random jitter to de-synchronize concurrent instances
    const jitter = Math.random() * Math.min(500, baseDelay * 0.2);
    const delay = Math.round(baseDelay + jitter);

    retryTimerRef.current = window.setTimeout(async () => {
      retryTimerRef.current = null;
      if (!mountedRef.current) return;
      setStatus("connecting");
      const { success, accepted } = await checkBackend();
      if (accepted && !success && mountedRef.current) {
        scheduleRetry();
      }
    }, delay);
  }, [checkBackend]);

  useEffect(() => {
    mountedRef.current = true;

    const attemptConnection = async () => {
      if (!mountedRef.current) return;
      const { success, accepted } = await checkBackend();
      if (accepted && !success && mountedRef.current) {
        scheduleRetry();
      }
    };

    attemptConnection();
    window.addEventListener("pywebviewready", attemptConnection);

    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      window.removeEventListener("pywebviewready", attemptConnection);
    };
  }, [checkBackend, scheduleRetry]);

  const retry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    retryCountRef.current = 0;
    setStatus("connecting");
    // Force a fresh attempt that supersedes any in-flight check.
    checkBackend(false).then(({ success, accepted }) => {
      if (accepted && !success && mountedRef.current) {
        scheduleRetry();
      }
    });
  }, [checkBackend, scheduleRetry]);

  const hasApi = status === "ready" || status === "degraded" || status === "connected";
  const isReady = status === "ready";
  const isConnecting = status === "connecting";
  const isConnected = hasApi;

  // Capability semantics:
  //   * hasApi (ready/degraded/connected) → bridge-backed file & settings ops
  //   * ready                            → renderer handshake confirmed
  const capabilities: BackendCapabilities = {
    canBrowse: hasApi,
    canScan: hasApi,
    canProbe: hasApi,
    canSaveSettings: hasApi,
    canOpenReport: hasApi,
    canPreview: isReady,
    canGenerate: isReady,
  };

  return { status, isConnected, hasApi, isReady, isConnecting, capabilities, retry };
}
