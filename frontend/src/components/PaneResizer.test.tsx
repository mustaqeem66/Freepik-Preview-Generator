import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PaneResizer } from "./PaneResizer";

describe("PaneResizer", () => {
  it("supports accessible keyboard adjustments", () => {
    const onChange = vi.fn();
    render(<PaneResizer label="Resize asset library" value={250} min={200} max={360} initial={250} onChange={onChange} />);
    const separator = screen.getByRole("separator", { name: "Resize asset library" });
    expect(separator.getAttribute("aria-valuenow")).toBe("250");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith(266);
    fireEvent.keyDown(separator, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith(200);
  });
  it("reverses inspector direction and supports reset", () => {
    const onChange = vi.fn();
    render(<PaneResizer label="Resize inspector" value={300} min={260} max={380} initial={300} reverse onChange={onChange} />);
    const separator = screen.getByRole("separator", { name: "Resize inspector" });
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith(316);
    fireEvent.doubleClick(separator);
    expect(onChange).toHaveBeenLastCalledWith(300);
  });
});
