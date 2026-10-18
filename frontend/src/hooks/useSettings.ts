import { useState, useEffect, useRef } from "react";
import { PreviewState } from "../types";
import { ApiBridge } from "../api/bridge";
import { SETTINGS_DEFAULTS, SETTINGS_FIELDS } from "../generated/settingsContract";

// Defaults derive from the generated contract so the frontend cannot drift from
// the canonical backend schema (previewgen/settings_schema.json).
export const defaultState: PreviewState = { ...SETTINGS_DEFAULTS } as PreviewState;

export function parseAndValidateSettings(raw: unknown): Partial<PreviewState> {
  if (!raw || typeof raw !== "object") return {};
  const data = raw as Record<string, unknown>;

  const validated: Record<string, unknown> = {};

  for (const field of SETTINGS_FIELDS) {
    const value = data[field.name];
    if (value === undefined || value === null) continue;

    if (field.type === "string") {
      if (typeof value !== "string") continue;
      if (field.enum && !field.enum.includes(value)) continue;
      if (field.pattern && !new RegExp(field.pattern).test(value)) continue;
      validated[field.name] = field.maxLength ? value.slice(0, field.maxLength) : value;
    } else if (field.type === "boolean") {
      if (typeof value !== "boolean") continue;
      validated[field.name] = value;
    } else if (field.type === "number" || field.type === "integer") {
      if (typeof value !== "number" || !Number.isFinite(value)) continue;
      let n = value;
      if (field.minimum !== undefined) n = Math.max(field.minimum, n);
      if (field.maximum !== undefined) n = Math.min(field.maximum, n);
      validated[field.name] = field.type === "integer" ? Math.round(n) : n;
    }
  }

  return validated as Partial<PreviewState>;
}

export function useSettings(onSaveError?: (err: string) => void, enabled = true) {
  const [state, setState] = useState<PreviewState>(defaultState);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);
  const revisionRef = useRef<number>(0);
  const onSaveErrorRef = useRef(onSaveError);
  onSaveErrorRef.current = onSaveError;
  useEffect(() => {
    if (!enabled || isLoaded) return;
    let unmounted = false;

    const loadSettings = async () => {
      const api = await ApiBridge.getApi(3000);
      if (api && !unmounted) {
        try {
          const res = await api.get_initial_state();
          const raw = res && "value" in res ? res.value : res;
          if (raw && typeof raw === "object" && "revision" in raw &&
              typeof raw.revision === "number" && Number.isSafeInteger(raw.revision)) {
            revisionRef.current = Math.max(revisionRef.current, raw.revision);
          }
          const validated = parseAndValidateSettings(raw);
          if (validated && !unmounted) {
            setState((prev) => ({ ...prev, ...validated }));
          }
        } catch (e) {
          console.error("Failed to restore settings:", e);
        } finally {
          if (!unmounted) setIsLoaded(true);
        }
      }
    };

    loadSettings();
    return () => {
      unmounted = true;
    };
  }, [enabled, isLoaded]);

  useEffect(() => {
    if (!isLoaded || !enabled) return;
    const currentRev = ++revisionRef.current;
    const timer = setTimeout(async () => {
      const api = await ApiBridge.getApi(1000);
      if (api && typeof api.save_settings === "function" && currentRev === revisionRef.current) {
        try {
          const res = await api.save_settings({ ...state, revision: currentRev });
          if (currentRev === revisionRef.current && res && "ok" in res && res.ok === false) {
            onSaveErrorRef.current?.(res.error || "Settings persistence rejected by backend.");
          }
        } catch (e) {
          if (currentRev === revisionRef.current) {
            const msg = e instanceof Error ? e.message : "Settings could not be saved.";
            onSaveErrorRef.current?.(msg);
          }
        }
      }
    }, 800);

    return () => clearTimeout(timer);
  }, [state, isLoaded, enabled]);

  return { state, setState, isLoaded };
}
