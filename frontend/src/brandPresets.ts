/** Browser-local style presets; never a source-read or export-write grant. */
import type { PreviewState } from "./types";
import { parseAndValidateSettings } from "./hooks/useSettings";

export const STYLE_PRESET_STORAGE_KEY = "previewgen.stylePresets.v1";
export const MAX_STYLE_PRESETS = 8;
const MAX_STORED_BYTES = 16_384;

// Explicit allowlist: do not persist paths or any key that authorizes access.
// Native logo/font grants must always come from the OS picker.
export const STYLE_FIELDS = [
  "invertTriangles", "solidColor", "autoFrame", "frameMargin",
  "text", "position", "textPosX", "textPosY", "textColor",
  "fontScale", "hasOutline", "outlineColor", "outlineThickness",
  "opacity", "logoScale", "logoOpacity", "logoPosX", "logoPosY",
  "modelColor", "yaw", "pitch", "outputWidth", "outputHeight",
] as const satisfies readonly (keyof PreviewState)[];

export interface StylePreset {
  name: string;
  styles: Partial<PreviewState>;
}

function safeName(raw: string): string {
  const trimmed = raw.replace(/[\u0000-\u001f\u007f]/g, " ").trim();
  if (!trimmed || trimmed.length > 40) {
    throw new Error("Preset name must be 1–40 characters.");
  }
  return trimmed;
}

export function safeStylePatch(source: unknown): Partial<PreviewState> {
  const clean = parseAndValidateSettings(source);
  const result: Record<string, unknown> = {};
  for (const key of STYLE_FIELDS) {
    const value = clean[key];
    if (value !== undefined) result[key] = value;
  }
  return result as Partial<PreviewState>;
}

export function parseStylePresets(raw: string | null): StylePreset[] {
  if (!raw || raw.length > MAX_STORED_BYTES) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return [];
    const data = parsed as { schemaVersion?: unknown; presets?: unknown };
    if (data.schemaVersion !== 1 || !Array.isArray(data.presets) ||
        data.presets.length > MAX_STYLE_PRESETS) return [];
    const collected: StylePreset[] = [];
    const seen = new Set<string>();
    for (const entry of data.presets) {
      if (!entry || typeof entry !== "object") return [];
      const record = entry as { name?: unknown; styles?: unknown };
      if (typeof record.name !== "string" ||
          !record.styles || typeof record.styles !== "object" ||
          Array.isArray(record.styles)) return [];
      const name = safeName(record.name);
      const normalized = name.toLocaleLowerCase("en");
      if (seen.has(normalized)) return [];
      seen.add(normalized);
      collected.push({ name, styles: safeStylePatch(record.styles) });
    }
    return collected;
  } catch {
    // Damaged or externally altered WebView storage never becomes authority.
    return [];
  }
}

export function readStylePresets(storage?: Pick<Storage, "getItem">): StylePreset[] {
  try {
    const store = storage ?? window.localStorage;
    return parseStylePresets(store.getItem(STYLE_PRESET_STORAGE_KEY));
  } catch {
    return [];
  }
}

export function putStylePreset(
  presets: readonly StylePreset[],
  name: string,
  currentState: PreviewState,
): StylePreset[] {
  const cleanName = safeName(name);
  const match = presets.findIndex(
    p => p.name.toLocaleLowerCase("en") === cleanName.toLocaleLowerCase("en")
  );
  if (match === -1 && presets.length >= MAX_STYLE_PRESETS) {
    throw new Error("Maximum eight style presets. Delete one before saving another.");
  }
  const next = presets.slice();
  const newPreset = { name: cleanName, styles: safeStylePatch(currentState) };
  if (match === -1) next.push(newPreset);
  else next[match] = newPreset;
  return next;
}

export function dropStylePreset(presets: readonly StylePreset[], name: string): StylePreset[] {
  return presets.filter(p => p.name !== name);
}

export function writeStylePresets(
  presets: readonly StylePreset[],
  storage?: Pick<Storage, "setItem">,
): void {
  const clean = parseStylePresets(JSON.stringify({ schemaVersion: 1, presets }));
  if (clean.length !== presets.length) throw new Error("Invalid style preset content.");
  const json = JSON.stringify({ schemaVersion: 1, presets: clean });
  if (json.length > MAX_STORED_BYTES) throw new Error("Style presets exceed the storage limit.");
  const store = storage ?? window.localStorage;
  store.setItem(STYLE_PRESET_STORAGE_KEY, json);
}
