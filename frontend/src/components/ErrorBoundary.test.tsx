import { describe, it, expect } from "vitest";
import React from "react";
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

    expect(screen.getByText("Application Render Error")).toBeInTheDocument();
    expect(screen.getByText("Simulated mount crash")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload Application" })).toBeInTheDocument();

    spy.mockRestore();
  });
});
