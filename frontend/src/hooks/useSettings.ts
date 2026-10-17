import { useState, useEffect } from "react";
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

export function parseAndValidateSettings(raw: unknown): Partial<PreviewState> {
  if (!raw || typeof raw !== "object") return {};
  const data = raw as Record<string, unknown>;

  const validated: Partial<PreviewState> = {};

  if (typeof data["text"] === "string") validated.text = data["text"].slice(0, 100);
  if (typeof data["inputFolder"] === "string") validated.inputFolder = data["inputFolder"];
  if (typeof data["outputFolder"] === "string") validated.outputFolder = data["outputFolder"];
  if (typeof data["sameFolder"] === "boolean") validated.sameFolder = data["sameFolder"];
  if (typeof data["invertTriangles"] === "boolean") validated.invertTriangles = data["invertTriangles"];
  if (typeof data["solidColor"] === "string" && /^#[0-9A-Fa-f]{6}$/.test(data["solidColor"])) {
    validated.solidColor = data["solidColor"];
  }
  if (typeof data["textColor"] === "string" && /^#[0-9A-Fa-f]{6}$/.test(data["textColor"])) {
    validated.textColor = data["textColor"];
  }
  if (typeof data["opacity"] === "number" && !isNaN(data["opacity"])) {
    validated.opacity = Math.max(0, Math.min(100, data["opacity"]));
  }
  if (typeof data["theme"] === "string" && (data["theme"] === "light" || data["theme"] === "dark")) {
    validated.theme = data["theme"];
  }
  if (
    typeof data["overwritePolicy"] === "string" &&
    ["rename", "skip", "overwrite"].includes(data["overwritePolicy"])
  ) {
    validated.overwritePolicy = data["overwritePolicy"] as "rename" | "skip" | "overwrite";
  }

  return validated;
}

export function useSettings(onSaveError?: (err: string) => void) {
  const [state, setState] = useState<PreviewState>(defaultState);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);

  useEffect(() => {
    let unmounted = false;

    const loadSettings = async () => {
      const api = await ApiBridge.getApi(3000);
      if (api && !unmounted) {
        try {
          const res = await api.get_initial_state();
          const raw = res && "value" in res ? res.value : res;
          const validated = parseAndValidateSettings(raw);
          if (validated && !unmounted) {
            setState((prev) => ({ ...prev, ...validated }));
          }
        } catch (e) {
          console.error("Failed to restore settings:", e);
        } finally {
          setIsLoaded(true);
        }
      }
    };

    loadSettings();
    return () => {
      unmounted = true;
    };
  }, []);

  useEffect(() => {
    if (!isLoaded) return;
    const timer = setTimeout(async () => {
      const api = await ApiBridge.getApi(1000);
      if (api) {
        try {
          const res = await api.save_settings(state);
          if (res && "ok" in res && res.ok === false) {
            onSaveError?.(res.error || "Settings persistence rejected by backend.");
          }
        } catch (e) {
          const msg = e instanceof Error ? e.message : "Settings could not be saved.";
          onSaveError?.(msg);
        }
      }
    }, 800);

    return () => clearTimeout(timer);
  }, [state, isLoaded, onSaveError]);

  return { state, setState, isLoaded };
}
