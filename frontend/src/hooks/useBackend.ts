import { useState, useEffect } from "react";
import { ApiBridge } from "../api/bridge";

export type BackendStatus = "connecting" | "connected" | "ready" | "degraded" | "disconnected";

export function useBackend() {
  const [status, setStatus] = useState<BackendStatus>("connecting");

  useEffect(() => {
    let unmounted = false;

    const checkBackend = async () => {
      const api = await ApiBridge.getApi(4000);
      if (unmounted) return;

      if (!api) {
        setStatus("disconnected");
        return;
      }

      setStatus("connected");
      try {
        if (api.frontend_ready) {
          const res = await api.frontend_ready();
          if (res && "ok" in res && res.ok === false) {
            setStatus("degraded");
            return;
          }
        }
        setStatus("ready");
      } catch (err) {
        console.warn("frontend_ready handshake warning:", err);
        setStatus("degraded");
      }
    };

    checkBackend();
    window.addEventListener("pywebviewready", checkBackend);

    return () => {
      unmounted = true;
      window.removeEventListener("pywebviewready", checkBackend);
    };
  }, []);

  const isConnected = status !== "disconnected";
  const isReady = status === "ready";

  return { status, isConnected, isReady };
}
