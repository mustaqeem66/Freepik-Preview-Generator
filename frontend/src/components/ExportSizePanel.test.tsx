import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { act } from "react";
import { ExportSizePanel, ExportSizePanelProps } from "./ExportSizePanel";
import { ApiBridge } from "../api/bridge";
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

  it("ignores an out-of-order backend dimension response", async () => {
    ApiBridge.clearCache();
    vi.useFakeTimers();
    try {
      const gates = new Map<number, ReturnType<typeof Promise.withResolvers<unknown>>>();
      const fakeApi = {
        calculate_export_dimensions: vi.fn(async (_path: string, w: number) => {
          const gate = Promise.withResolvers<unknown>();
          gates.set(w, gate);
          return gate.promise.then(() => ({ ok: true, value: { width: w, height: w } }));
        }),
      };
      // @ts-expect-error mock window.pywebview
      window.pywebview = { api: fakeApi };

      const props = setup({ filePath: "a.png" });
      fireEvent.change(screen.getByTestId("output-width"), { target: { value: "800" } });
      // The locally computed size commits at once: an export started inside the
      // debounce window must never be written at the previously chosen size.
      expect(props.onChange).toHaveBeenLastCalledWith(800, 800);
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(fakeApi.calculate_export_dimensions).toHaveBeenCalledTimes(1);

      // A newer keystroke supersedes the pending request before it resolves
      fireEvent.change(screen.getByTestId("output-width"), { target: { value: "900" } });
      expect(props.onChange).toHaveBeenLastCalledWith(900, 900);
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(fakeApi.calculate_export_dimensions).toHaveBeenCalledTimes(2);

      // The stale 800 response lands first: generation guard must discard it
      const callsBeforeStale = vi.mocked(props.onChange).mock.calls.length;
      await act(async () => { gates.get(800)!.resolve(undefined); });
      expect(props.onChange).toHaveBeenCalledTimes(callsBeforeStale);

      await act(async () => { gates.get(900)!.resolve(undefined); });
      expect(props.onChange).toHaveBeenLastCalledWith(900, 900);
    } finally {
      vi.useRealTimers();
      ApiBridge.clearCache();
      delete window.pywebview;
    }
  });

  it("discards a pending backend reconcile when Original is chosen", async () => {
    ApiBridge.clearCache();
    vi.useFakeTimers();
    try {
      const gates = new Map<number, ReturnType<typeof Promise.withResolvers<unknown>>>();
      const fakeApi = {
        calculate_export_dimensions: vi.fn(async (_path: string, w: number) => {
          const gate = Promise.withResolvers<unknown>();
          gates.set(w, gate);
          return gate.promise.then(() => ({ ok: true, value: { width: w, height: w } }));
        }),
      };
      // @ts-expect-error mock window.pywebview
      window.pywebview = { api: fakeApi };

      const props = setup({ filePath: "a.png" });
      fireEvent.change(screen.getByTestId("output-width"), { target: { value: "800" } });
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(fakeApi.calculate_export_dimensions).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByTestId("preset-0"));
      expect(props.onChange).toHaveBeenLastCalledWith(0, 0);
      const callsAfterOriginal = vi.mocked(props.onChange).mock.calls.length;

      // The in-flight 800 reply must not re-size the export back to 800
      await act(async () => { gates.get(800)!.resolve(undefined); });
      expect(props.onChange).toHaveBeenCalledTimes(callsAfterOriginal);
      expect(props.onChange).toHaveBeenLastCalledWith(0, 0);
    } finally {
      vi.useRealTimers();
      ApiBridge.clearCache();
      delete window.pywebview;
    }
  });

  it("drops a pending dimension reply when the selected asset changes", async () => {
    ApiBridge.clearCache();
    vi.useFakeTimers();
    try {
      const gate = Promise.withResolvers<unknown>();
      const fakeApi = {
        calculate_export_dimensions: vi.fn(async () =>
          gate.promise.then(() => ({ ok: true, value: { width: 800, height: 800 } }))),
      };
      // @ts-expect-error mock window.pywebview
      window.pywebview = { api: fakeApi };

      const props: ExportSizePanelProps = {
        filePath: "a.png", probe: vectorProbe, isProbing: false, aspectWidth: 256, aspectHeight: 256,
        outputWidth: 0, outputHeight: 0, onChange: vi.fn(), onExport: vi.fn(),
        canExport: true, isExporting: false, disabled: false,
      };
      const view = render(<ExportSizePanel {...props} />);
      fireEvent.click(screen.getByTestId("export-size-toggle"));
      fireEvent.change(screen.getByTestId("output-width"), { target: { value: "800" } });
      await act(async () => { await vi.advanceTimersByTimeAsync(200); });
      expect(fakeApi.calculate_export_dimensions).toHaveBeenCalledTimes(1);

      view.rerender(<ExportSizePanel {...props} filePath="b.png" />);
      const callsAfterSwitch = vi.mocked(props.onChange).mock.calls.length;

      // Reply for the abandoned asset must not size the new asset's export
      await act(async () => { gate.resolve(undefined); });
      expect(props.onChange).toHaveBeenCalledTimes(callsAfterSwitch);
    } finally {
      vi.useRealTimers();
      ApiBridge.clearCache();
      delete window.pywebview;
    }
  });
});
