import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiBridge } from "../api/bridge";
import { DesktopTitlebar } from "./DesktopTitlebar";

afterEach(() => { vi.restoreAllMocks(); });

async function setup(platform: "windows" | "linux" | "macos", enabled = true) {
  const window_action = vi.fn(async () => ({ ok: true, error: null }));
  vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
    get_window_chrome: async () => ({ ok: true, value: { enabled, platform }, error: null }),
    window_action,
  } as never);
  render(<DesktopTitlebar />);
  if (enabled) await waitFor(() => expect(screen.getByTestId("desktop-titlebar")).toBeTruthy());
  return window_action;
}

describe("platform titlebar", () => {
  it("uses left minimize/fullscreen and right close on Windows and Linux", async () => {
    for (const platform of ["windows", "linux"] as const) {
      const call = await setup(platform);
      const leading = document.querySelector(".titlebar-leading")!;
      const trailing = document.querySelector(".titlebar-trailing")!;
      expect(leading.querySelector('[aria-label="Minimize window"]')).toBeTruthy();
      expect(leading.querySelector('[aria-label="Toggle fullscreen"]')).toBeTruthy();
      expect(trailing.querySelector('[aria-label="Close application"]')).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Minimize window" }));
      await waitFor(() => expect(call).toHaveBeenCalledWith("minimize"));
      screen.getByTestId("desktop-titlebar").remove();
    }
  });

  it("places all three buttons on the right on macOS", async () => {
    const call = await setup("macos");
    const trailing = document.querySelector(".titlebar-trailing")!;
    expect(trailing.querySelectorAll("button")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Toggle fullscreen" }));
    await waitFor(() => expect(call).toHaveBeenCalledWith("fullscreen"));
  });

  it("renders no fake controls when OS titlebar is active", async () => {
    await setup("linux", false);
    expect(screen.queryByTestId("desktop-titlebar")).toBeNull();
  });
});
