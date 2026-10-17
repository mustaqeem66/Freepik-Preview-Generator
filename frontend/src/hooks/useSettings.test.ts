import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useSettings } from "./useSettings";

describe("useSettings hook", () => {
  it("initializes with isLoaded false and reacts to true upon loading", async () => {
    const fakeApi = {
      get_initial_state: async () => ({
        ok: true,
        value: { text: "CUSTOM WATERMARK", theme: "dark" },
        error: null,
      }),
      save_settings: async () => ({ ok: true, value: true, error: null }),
    };
    // @ts-expect-error mock window.pywebview
    window.pywebview = { api: fakeApi };

    const { result } = renderHook(() => useSettings());
    expect(result.current.isLoaded).toBe(false);

    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    expect(result.current.state.text).toBe("CUSTOM WATERMARK");
    expect(result.current.state.theme).toBe("dark");
  });
});
