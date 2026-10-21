import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
