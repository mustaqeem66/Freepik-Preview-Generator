import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { CanvasExportDock } from "./CanvasExportDock";

const props = {
  isProcessing: false,
  progress: { current: 0, total: 0, message: "Ready to process" },
  stats: { success: 0, failed: 0 },
  batchErrors: [],
  onStartBatch: vi.fn(),
  onCancelBatch: vi.fn(),
  canStart: false,
  canOpenOutput: false,
  onOpenOutput: vi.fn(),
};

describe("CanvasExportDock", () => {
  it("renders export and output commands in one labeled canvas dock", () => {
    const start = vi.fn();
    const open = vi.fn();
    render(<CanvasExportDock {...props} canStart canOpenOutput
      onStartBatch={start} onOpenOutput={open} />);
    const region = screen.getByRole("region", { name: "Batch export actions" });
    expect(region.classList.contains("canvas-export-dock")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Generate Previews" }));
    fireEvent.click(screen.getByRole("button", { name: "Open output folder" }));
    expect(start).toHaveBeenCalledOnce();
    expect(open).toHaveBeenCalledOnce();
  });

  it("cannot open outputs or generate while prerequisites are missing", () => {
    render(<CanvasExportDock {...props}/>);
    expect(screen.getByRole("button", { name: "Generate Previews" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Open output folder" })).toBeDisabled();
  });

  it("preserves cancellation during a running batch", () => {
    const cancel = vi.fn();
    render(<CanvasExportDock {...props} isProcessing onCancelBatch={cancel}
      progress={{ current: 2, total: 5, message: "Rendering 2 of 5" }} />);
    expect(screen.queryByRole("button", { name: "Generate Previews" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Batch" }));
    expect(cancel).toHaveBeenCalledOnce();
  });
});
