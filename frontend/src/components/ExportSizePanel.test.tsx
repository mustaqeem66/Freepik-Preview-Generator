import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExportSizePanel, ExportSizePanelProps } from "./ExportSizePanel";
import { AssetProbe } from "../types";

const vectorProbe: AssetProbe = {
  kind: "vector",
  resizable: true,
  nativeWidth: 256,
  nativeHeight: 256,
  maxDimension: 8192,
  defaultDimension: 2400,
};

const rasterProbe: AssetProbe = {
  kind: "raster",
  resizable: false,
  nativeWidth: 1000,
  nativeHeight: 1000,
  maxDimension: 8192,
  defaultDimension: 2400,
};

function setup(overrides: Partial<ExportSizePanelProps> = {}) {
  const props: ExportSizePanelProps = {
    probe: vectorProbe,
    isProbing: false,
    aspectWidth: 256,
    aspectHeight: 256,
    outputWidth: 0,
    outputHeight: 0,
    onChange: vi.fn(),
    onExport: vi.fn(),
    canExport: true,
    isExporting: false,
    disabled: false,
    ...overrides,
  };
  render(<ExportSizePanel {...props} />);
  fireEvent.click(screen.getByTestId("export-size-toggle"));
  return props;
}

describe("ExportSizePanel", () => {

  it("disables presets above a raster's native resolution", () => {
    setup({ probe: { ...rasterProbe, nativeWidth: 3000, nativeHeight: 3000 } });
    expect((screen.getByTestId("preset-4096") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("preset-2048") as HTMLButtonElement).disabled).toBe(false);
  });

  it("locks the aspect ratio and derives the paired dimension", () => {
    const props = setup({ aspectWidth: 1000, aspectHeight: 500 });
    fireEvent.change(screen.getByTestId("output-width"), { target: { value: "800" } });
    expect(props.onChange).toHaveBeenCalledWith(800, 400);
  });

  it("clamps a width request above a raster's native size", () => {
    const props = setup({ probe: rasterProbe });
    fireEvent.change(screen.getByTestId("output-width"), { target: { value: "5000" } });
    expect(props.onChange).toHaveBeenCalledWith(1000, 1000);
  });

  it("resets to original (0,0) via the Original preset", () => {
    const props = setup({ outputWidth: 2048, outputHeight: 2048 });
    fireEvent.click(screen.getByTestId("preset-0"));
    expect(props.onChange).toHaveBeenCalledWith(0, 0);
  });


  it("disables export when the backend is not ready", () => {
    setup({ canExport: false });
    expect((screen.getByTestId("export-preview") as HTMLButtonElement).disabled).toBe(true);
  });

  it("disables the toggle when no asset is selected", () => {
    setup({ disabled: true });
    expect((screen.getByTestId("export-size-toggle") as HTMLButtonElement).disabled).toBe(true);
  });
});
