import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { defaultState } from "./hooks/useSettings";
import {
  MAX_STYLE_PRESETS, parseStylePresets, putStylePreset, safeStylePatch,
  STYLE_PRESET_STORAGE_KEY, readStylePresets, writeStylePresets,
} from "./brandPresets";
import { StylePresetManager } from "./components/StylePresetManager";

describe("grant-safe style presets", () => {
  beforeEach(() => window.localStorage.clear());

  it("never captures file grants, private source or export paths", () => {
    const state = {
      ...defaultState, text: "Brand A", solidColor: "#112233",
      logoPath: "C:/private/logo.png", fontPath: "/home/private/font.otf",
      inputFolder: "/private/input", outputFolder: "/private/output",
      sameFolder: true,
    };
    const saved = putStylePreset([], "Marketplace", state);
    expect(saved).toHaveLength(1);
    expect(saved[0].styles).toMatchObject({ text: "Brand A", solidColor: "#112233" });
    const keys = Object.keys(saved[0].styles);
    for (const forbidden of ["logoPath", "fontPath", "inputFolder", "outputFolder", "sameFolder", "overwritePolicy"]) {
      expect(keys).not.toContain(forbidden);
    }
    writeStylePresets(saved);
    const raw = window.localStorage.getItem(STYLE_PRESET_STORAGE_KEY) || "";
    expect(raw).not.toContain("private");
    expect(raw).not.toContain("logoPath");
    expect(readStylePresets()).toEqual(saved);
  });

  it("revalidates tampered local storage and clips bounded numeric style values", () => {
    const untrusted = JSON.stringify({
      schemaVersion: 1,
      presets: [{ name: "Allowed", styles: {
        logoPath: "/ungranted/secret.png", inputFolder: "/bad",
        solidColor: "#ABCDEF", opacity: 9999, text: "x".repeat(300),
        hiddenGrant: true,
      } }],
    });
    const parsed = parseStylePresets(untrusted);
    expect(parsed[0].styles).toEqual({
      solidColor: "#ABCDEF", opacity: 100, text: "x".repeat(100),
    });
    expect(safeStylePatch({ fontPath: "C:\\forbidden.ttf", opacity: NaN })).toEqual({});
    expect(parseStylePresets("{invalid JSON")).toEqual([]);
  });

  it("limits to eight, rejects bad names and overwrites same-name styles", () => {
    let presets = [];
    for (let i = 0; i < MAX_STYLE_PRESETS; i++) {
      presets = putStylePreset(presets, `Brand ${i}`, defaultState);
    }
    expect(presets).toHaveLength(8);
    expect(() => putStylePreset(presets, "Brand 8", defaultState)).toThrow(/maximum eight/i);
    expect(() => putStylePreset([], "\n\t", defaultState)).toThrow(/preset name/i);
    const overwritten = putStylePreset(presets, "brand 0", {
      ...defaultState, text: "Updated",
    });
    expect(overwritten).toHaveLength(8);
    expect(overwritten[0].styles.text).toBe("Updated");
  });

  it("shows save and apply controls, preserves actual logo grant in current state", () => {
    const onChange = vi.fn();
    const original = { ...defaultState, text: "PRIMARY", logoPath: "/granted/logo.png" };
    const view = render(<StylePresetManager state={original} onChange={onChange} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Style preset name" }),
      { target: { value: "Clean" } });
    fireEvent.click(screen.getByRole("button", { name: "Save style" }));
    expect(screen.getByRole("option", { name: "Clean" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Saved style preset" }),
      { target: { value: "Clean" } });
    view.rerender(<StylePresetManager state={{ ...original, text: "OTHER" }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply style" }));
    const applied = onChange.mock.calls[0][0];
    expect(applied.text).toBe("PRIMARY");
    expect(applied).not.toHaveProperty("logoPath");
    expect(applied).not.toHaveProperty("inputFolder");
    fireEvent.click(screen.getByRole("button", { name: "Delete style" }));
    expect(readStylePresets()).toEqual([]);
  });
});
