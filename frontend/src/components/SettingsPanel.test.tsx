import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { SettingsPanel } from "./SettingsPanel";
import type { PreviewState } from "../types";

const STATE: PreviewState = {
  inputFolder: "/assets", outputFolder: "/exports", sameFolder: false, invertTriangles: true,
  solidColor: "#FFFFFF", logoPath: "", logoScale: 100, logoOpacity: 100, logoPosX: 50, logoPosY: 50,
  text: "Studio", textPosX: 50, textPosY: 50, textColor: "#000000", fontPath: "", fontScale: 100,
  hasOutline: false, outlineColor: "#000000", outlineThickness: 2, opacity: 100, yaw: 45, pitch: 30,
  theme: "light", desktopNotifications: false, overwritePolicy: "rename", outputWidth: 2400, outputHeight: 2400,
};

function renderPanel(is3D = false) {
  return render(<SettingsPanel state={STATE} onChange={() => {}} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={is3D} />);
}

describe("SettingsPanel", () => {
  beforeEach(() => localStorage.clear());

  it("renders main sections", () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: /background/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /watermark/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /brand logo/i })).toBeInTheDocument();
  });

  it("shows the camera section only for 3D assets", () => {
    renderPanel(false);
    expect(screen.queryByText(/3d camera/i)).not.toBeInTheDocument();
  });
  it("styles native range inputs with a bounded percentage and context hints", () => {
    const onChange = vi.fn();
    render(<SettingsPanel state={{ ...STATE, opacity: 73, fontScale: 100 }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const opacity = screen.getByRole("slider", { name: "Text opacity" }) as HTMLInputElement;
    expect(opacity.closest(".precision-slider")).toBeTruthy();
    expect(opacity.style.getPropertyValue("--slider-progress")).toBe("73%");
    expect(screen.getByText("Subtle")).toBeInTheDocument();
    expect(screen.getByText("Balanced")).toBeInTheDocument();
    const scale = screen.getByRole("slider", { name: "Font scale" }) as HTMLInputElement;
    expect(parseFloat(scale.style.getPropertyValue("--slider-progress"))).toBeCloseTo(28.57, 1);
    fireEvent.change(opacity, { target: { value: "45" } });
    expect(onChange).toHaveBeenCalledWith({ opacity: 45 });
  });

  it("keeps the same accessible slider behavior in light and dark appearance", () => {
    const onChange = vi.fn();
    for (const theme of ["light", "dark"] as const) {
      document.documentElement.setAttribute("data-theme", theme);
      const ui = render(<SettingsPanel state={{ ...STATE, theme, opacity: 90 }}
        onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={true} />);
      const slider = screen.getByRole("slider", { name: "Text opacity" }) as HTMLInputElement;
      expect(slider.getAttribute("min")).toBe("0");
      expect(slider.getAttribute("max")).toBe("100");
      expect(slider.value).toBe("90");
      expect(slider.closest(".precision-slider-track")).toBeTruthy();
      expect(screen.getByRole("slider", { name: "Pitch elevation" })).toBeInTheDocument();
      ui.unmount();
    }
    document.documentElement.removeAttribute("data-theme");
  });

});
