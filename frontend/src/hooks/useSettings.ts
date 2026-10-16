import { useState, useEffect, useRef } from "react";
import { PreviewState } from "../types";
import { ApiBridge } from "../api/bridge";

export const defaultState: PreviewState = {
  inputFolder: "",
  outputFolder: "",
  sameFolder: false,
  invertTriangles: true,
  solidColor: "#FFFFFF",
  logoPath: "",
  logoScale: 100,
  logoOpacity: 90,
  logoPosX: 88,
  logoPosY: 5,
  text: "100% TRANSPARENT",
  textPosX: 5,
  textPosY: 5,
  textColor: "#FFFFFF",
  fontPath: "",
  fontScale: 100,
  hasOutline: true,
  outlineColor: "#000000",
  outlineThickness: 2,
  opacity: 90,
  yaw: 45,
  pitch: 30,
  theme: "light",
  overwritePolicy: "rename",
};

export function useSettings() {
  const [state, setState] = useState<PreviewState>(defaultState);
  const isLoadedRef = useRef<boolean>(false);

  useEffect(() => {
    let unmounted = false;

    const loadSettings = async () => {
      const api = await ApiBridge.getApi(3000);
      if (api && !unmounted) {
        try {
          const res = await api.get_initial_state();
          const saved: Partial<PreviewState> | undefined =
            res && "value" in res ? res.value : (res as Partial<PreviewState>);
          if (saved && !unmounted) {
            setState((prev) => ({ ...prev, ...saved }));
          }
        } catch (e) {
          console.error("Failed to restore settings:", e);
        } finally {
          isLoadedRef.current = true;
        }
      }
    };

    loadSettings();
    return () => {
      unmounted = true;
    };
  }, []);

  useEffect(() => {
    if (!isLoadedRef.current) return;
    const timer = setTimeout(async () => {
      const api = await ApiBridge.getApi(1000);
      if (api) {
        try {
          await api.save_settings(state);
        } catch (e) {
          console.warn("Failed to persist settings:", e);
        }
      }
    }, 800);

    return () => clearTimeout(timer);
  }, [state]);

  return { state, setState, isLoaded: isLoadedRef.current };
}
