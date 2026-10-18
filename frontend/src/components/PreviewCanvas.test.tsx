import { describe, it, expect } from "vitest";

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { PreviewCanvas } from "./PreviewCanvas";

describe("PreviewCanvas Component", () => {

  it("renders error alert on render failure", () => {
    render(
      <PreviewCanvas
        previewUrl={null}
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
