import { useState, useEffect } from "react";
import { ApiBridge } from "../api/bridge";

export function useBackend() {
  const [isConnected, setIsConnected] = useState<boolean>(true);
  const [isReady, setIsReady] = useState<boolean>(false);

  useEffect(() => {
    let unmounted = false;

    const checkBackend = async () => {
      const api = await ApiBridge.getApi(4000);
      if (unmounted) return;

      if (api) {
        setIsConnected(true);
        try {
          if (api.frontend_ready) {
            await api.frontend_ready();
          }
          setIsReady(true);
        } catch (e) {
          console.warn("frontend_ready warning:", e);
          setIsReady(true);
        }
      } else {
        setIsConnected(false);
      }
    };

    checkBackend();
    window.addEventListener("pywebviewready", checkBackend);

    return () => {
      unmounted = true;
      window.removeEventListener("pywebviewready", checkBackend);
    };
  }, []);

  return { isConnected, isReady };
}
