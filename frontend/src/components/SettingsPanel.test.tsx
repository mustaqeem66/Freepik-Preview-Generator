import { beforeEach, describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
