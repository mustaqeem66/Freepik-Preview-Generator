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

  it("enables opt-in subject framing without changing existing defaults", () => {
    const onChange = vi.fn();
    const ui = render(<SettingsPanel state={{ ...STATE, autoFrame: false, frameMargin: 8 }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const checkbox = screen.getByRole("checkbox", { name: "Auto-frame transparent subject" });
    expect(checkbox).not.toBeChecked();
    expect(screen.queryByRole("slider", { name: "Subject margin" })).not.toBeInTheDocument();
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith({ autoFrame: true });

    ui.rerender(<SettingsPanel state={{ ...STATE, autoFrame: true, frameMargin: 8 }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const slider = screen.getByRole("slider", { name: "Subject margin" });
    fireEvent.change(slider, { target: { value: "12" } });
    expect(onChange).toHaveBeenCalledWith({ frameMargin: 12 });
  });

  it("exposes a default-off animated contact sheet without affecting other controls", () => {
    const onChange = vi.fn();
    const panel = render(<SettingsPanel state={{ ...STATE, animationContactSheet: false }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const toggle = screen.getByRole("checkbox", { name: "Animated GIF/WebP contact sheet" });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith({ animationContactSheet: true });
    panel.rerender(<SettingsPanel state={{ ...STATE, animationContactSheet: true }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    expect(screen.getByText(/Shows up to nine GIF\/WebP frames/)).toBeInTheDocument();
  });

  it("offers a default-off Procreate brushset contact-sheet setting", () => {
    const onChange = vi.fn();
    const ui = render(<SettingsPanel state={{ ...STATE, brushsetContactSheet: false }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const toggle = screen.getByRole("checkbox", { name: "Procreate brushset contact sheet" });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith({ brushsetContactSheet: true });
    ui.rerender(<SettingsPanel state={{ ...STATE, brushsetContactSheet: true }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    expect(screen.getByText(/previews up to nine tips/)).toBeInTheDocument();
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

  it("offers backend-supported watermark placements and hides custom sliders for presets", () => {
    const onChange = vi.fn();
    const { rerender } = render(<SettingsPanel state={{ ...STATE, position: "custom" }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    const placement = screen.getByRole("combobox", { name: "Watermark placement" });
    fireEvent.change(placement, { target: { value: "center" } });
    expect(onChange).toHaveBeenCalledWith({ position: "center" });
    rerender(<SettingsPanel state={{ ...STATE, position: "center" }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    expect(screen.queryByRole("slider", { name: "Text X" })).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "Text Y" })).not.toBeInTheDocument();
  });

  it("offers optional tiled diagonal watermarking without custom coordinates", () => {
    const onChange = vi.fn();
    const { rerender } = render(<SettingsPanel state={{ ...STATE, position: "custom" }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Watermark placement" }),
      { target: { value: "tiled" } });
    expect(onChange).toHaveBeenCalledWith({ position: "tiled" });
    rerender(<SettingsPanel state={{ ...STATE, position: "tiled" }}
      onChange={onChange} onBrowseLogo={() => {}} onBrowseFont={() => {}} is3D={false} />);
    expect(screen.queryByRole("slider", { name: "Text X" })).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "Text Y" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tiled diagonal" })).toBeInTheDocument();
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
