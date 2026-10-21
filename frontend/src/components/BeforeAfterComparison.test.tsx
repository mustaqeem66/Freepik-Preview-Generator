import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { BeforeAfterComparison } from "./BeforeAfterComparison";

describe("BeforeAfterComparison", () => {
  const props = {
    sourceUrl: "http://127.0.0.1:8001/source.jpg",
    previewUrl: "http://127.0.0.1:8001/after.jpg",
    name: "artwork.png",
    onClose: vi.fn(),
  };

  it("labels source and generated JPG distinctly without reading local file paths", () => {
    render(<BeforeAfterComparison {...props} />);
    expect(screen.getByRole("group", { name: /Source versus Preview/ })).toBeTruthy();
    expect(screen.getByAltText(/Before: source artwork/).getAttribute("src")).toBe(props.sourceUrl);
    expect(screen.getByAltText(/After: PreviewGen JPG/).getAttribute("src")).toBe(props.previewUrl);
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toContain("50%");
  });

  it("supports native keyboard and pointer range changes", () => {
    render(<BeforeAfterComparison {...props} />);
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "80" } });
    expect(slider).toHaveProperty("value", "80");
    expect(slider.getAttribute("aria-valuetext")).toContain("80%");
    expect(screen.getByText("80% source · 20% preview")).toBeTruthy();
  });

  it("resets comparison when a new image pair is selected", () => {
    const { rerender } = render(<BeforeAfterComparison {...props} />);
    fireEvent.change(screen.getByRole("slider"), { target: { value: "5" } });
    rerender(<BeforeAfterComparison {...props} sourceUrl="http://127.0.0.1:8001/new-source.jpg" />);
    expect(screen.getByRole("slider")).toHaveProperty("value", "50");
  });

  it("offers a safe return to preview after a missing image", () => {
    const onClose = vi.fn();
    render(<BeforeAfterComparison {...props} onClose={onClose} />);
    fireEvent.error(screen.getByAltText(/Before: source artwork/));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Return to preview" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
