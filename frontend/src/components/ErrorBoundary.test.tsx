import { describe, it, expect } from "vitest";

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ErrorBoundary } from "./ErrorBoundary";

const ProblemChild = () => {
  throw new Error("Simulated mount crash");
};

describe("ErrorBoundary Component", () => {
  it("catches render errors and renders graceful recovery UI", () => {
    // Suppress expected console.error during error boundary test
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ProblemChild />
      </ErrorBoundary>
    );

    expect(screen.getByText("PreviewGen could not load its interface")).toBeInTheDocument();
    expect(screen.getByText("Simulated mount crash")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart PreviewGen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Details" })).toBeInTheDocument();

    spy.mockRestore();
  });
});
