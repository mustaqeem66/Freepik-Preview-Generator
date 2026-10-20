import { describe, it, expect, vi } from "vitest";

import { render, screen, fireEvent } from "@testing-library/react";
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
  it("offers a keyboard-accessible source folder action only on first run", () => {
    const choose = vi.fn();
    const view = render(<PreviewCanvas previewUrl={null} isLoading={false} renderError={null}
      name="" width={0} height={0} onChooseFolder={choose} canChooseFolder />);
    fireEvent.click(screen.getByRole("button", { name: "Choose Input Folder" }));
    expect(choose).toHaveBeenCalledTimes(1);
    view.rerender(<PreviewCanvas previewUrl={null} isLoading={false} renderError={null}
      name="" width={0} height={0} onChooseFolder={choose} canChooseFolder hasSourceFolder />);
    expect(screen.queryByRole("button", { name: "Choose Input Folder" })).toBeNull();
    expect(screen.getByText("No preview selected")).toBeInTheDocument();
  });

});
