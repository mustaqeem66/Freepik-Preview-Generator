import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useSettings, parseAndValidateSettings } from "./useSettings";
import { ApiBridge } from "../api/bridge";

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

  it("stamps every persisted update with a strictly increasing revision", async () => {
    ApiBridge.clearCache();
    const revisions: number[] = [];
    const fakeApi = {
      get_initial_state: async () => ({ ok: true, value: {}, error: null }),
      save_settings: async (settings: { revision?: number }) => {
        revisions.push(settings.revision as number);
        return { ok: true, value: true, error: null };
      },
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.isLoaded).toBe(true));

    await waitFor(() => expect(revisions.length).toBeGreaterThanOrEqual(1), { timeout: 2000 });
    await act(async () => {
      result.current.setState((prev) => ({ ...prev, text: "first" }));
    });
    await waitFor(() => expect(revisions.length).toBeGreaterThanOrEqual(2), { timeout: 2000 });
    await act(async () => {
      result.current.setState((prev) => ({ ...prev, text: "second" }));
    });
    await waitFor(() => expect(revisions.length).toBeGreaterThanOrEqual(3), { timeout: 2000 });

    for (let i = 1; i < revisions.length; i++) {
      expect(revisions[i]).toBeGreaterThan(revisions[i - 1]);
    }
  });
});
