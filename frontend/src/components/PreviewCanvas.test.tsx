import { describe, it, expect } from "vitest";

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { PreviewCanvas } from "./PreviewCanvas";

describe("PreviewCanvas Component", () => {
  it("renders preview image when dataUrl is present", () => {
    render(
      <PreviewCanvas
        previewDataUrl="data:image/jpeg;base64,TEST_DATA"
        isLoading={false}
        renderError={null}
        name="sample.png"
        width={800}
        height={600}
      />
    );

    const img = screen.getByRole("img", { name: "sample.png" });
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "data:image/jpeg;base64,TEST_DATA");
    expect(screen.getByText(/sample.png \(800 × 600\)/)).toBeInTheDocument();
  });

  it("renders error alert on render failure", () => {
    render(
      <PreviewCanvas
        previewDataUrl={null}
        isLoading={false}
        renderError="Corrupt PSD header"
        name="sample.psd"
        width={0}
        height={0}
      />
    );

    expect(screen.getByText(/Corrupt PSD header/)).toBeInTheDocument();
  });
});
