import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useSettings, parseAndValidateSettings } from "./useSettings";

describe("useSettings hook", () => {
  it("parses and validates schema fields while dropping invalid properties", () => {
    const raw = {
      text: "Valid Watermark",
      solidColor: "#FF0000",
      opacity: 85,
      theme: "dark",
      overwritePolicy: "rename",
      bogusField: "should be dropped",
      invalidColor: "not-a-hex",
    };
    const validated = parseAndValidateSettings(raw);
    expect(validated.text).toBe("Valid Watermark");
    expect(validated.solidColor).toBe("#FF0000");
    expect(validated.opacity).toBe(85);
    expect(validated.theme).toBe("dark");
    expect(validated.overwritePolicy).toBe("rename");
    expect((validated as Record<string, unknown>)["bogusField"]).toBeUndefined();
  });

  it("triggers onSaveError callback when persistence fails", async () => {
    const onSaveError = vi.fn();
    const fakeApi = {
      get_initial_state: async () => ({ ok: true, value: {}, error: null }),
      save_settings: async () => ({ ok: false, value: false, error: "Disk write failure" }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useSettings(onSaveError));

    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });

    // Wait for debounced save
    await waitFor(
      () => {
        expect(onSaveError).toHaveBeenCalled();
      },
      { timeout: 1500 }
    );
  });
});
