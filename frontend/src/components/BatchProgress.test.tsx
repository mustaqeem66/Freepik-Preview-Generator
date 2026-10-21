import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { BatchProgress } from "./BatchProgress";

const base = {
  isProcessing: true,
  progress: { current: 1, total: 3, message: "Processing" },
  stats: { success: 0, failed: 0 },
  batchErrors: [],
  onStartBatch: vi.fn(),
  onCancelBatch: vi.fn(),
  canStart: false,
};

describe("BatchProgress cancellation controls", () => {
  it("disables cancellation while waiting for batch startup", () => {
    render(<BatchProgress {...base} canCancelBatch={false} />);
    const button = screen.getByRole("button", { name: "Starting…" });
    expect(button.hasAttribute("disabled")).toBe(true);
  });
  it("disables repeat clicks once cancellation is in progress", () => {
    render(<BatchProgress {...base} canCancelBatch={false} isCancelling />);
    const button = screen.getByRole("button", { name: "Cancelling…" });
    expect(button.hasAttribute("disabled")).toBe(true);
  });
  it("keeps idle progress text with the action rather than an empty footer", () => {
    const start = vi.fn();
    render(<BatchProgress {...base} isProcessing={false} canStart onStartBatch={start}
      progress={{ current: 0, total: 0, message: "Ready to process" }} />);
    const region = screen.getByRole("region", { name: "Batch generation" });
    expect(region.querySelector(".bp-main")).not.toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Ready to process");
    fireEvent.click(screen.getByRole("button", { name: "Generate Previews" }));
    expect(start).toHaveBeenCalledOnce();
  });

  it("keeps in-progress status and cancellation accessible", () => {
    render(<BatchProgress {...base} />);
    expect(screen.getByRole("progressbar", { name: "Batch generation progress" })
      .getAttribute("aria-valuenow")).toBe("33");
    expect(screen.getByRole("button", { name: "Cancel Batch" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Processing");
  });

});
