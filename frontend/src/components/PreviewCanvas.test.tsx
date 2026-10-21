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

  it("zooms relative to fitted preview and resets when selecting a different asset", () => {
    const renderPreview = (url: string) => <PreviewCanvas previewUrl={url} isLoading={false}
      renderError={null} name="image.png" width={800} height={600} />;
    const view = render(renderPreview("http://127.0.0.1:4242/a.jpg"));
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByText("125% of fit")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fit preview" }));
    expect(screen.getByText("100% of fit")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    view.rerender(renderPreview("http://127.0.0.1:4242/b.jpg"));
    expect(screen.getByText("100% of fit")).toBeInTheDocument();
  });
});
