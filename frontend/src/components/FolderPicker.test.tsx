import { describe, it, expect } from "vitest";

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { FolderPicker } from "./FolderPicker";

describe("FolderPicker Component", () => {

  it("disables output folder selection when sameFolder is active", () => {
    render(
      <FolderPicker
        inputFolder="/path/to/assets"
        outputFolder=""
        sameFolder={true}
        onBrowseInput={() => {}}
        onBrowseOutput={() => {}}
        onToggleSameFolder={() => {}}
      />
    );

    const outputBtn = screen.getByRole("button", { name: /choose output folder/i });
    expect(outputBtn).toBeDisabled();
  });

  it("only allows the output folder to be chosen through the native picker", () => {
    render(
      <FolderPicker
        inputFolder="/path/to/assets"
        outputFolder="/path/to/exports"
        sameFolder={false}
        onBrowseInput={() => {}}
        onBrowseOutput={() => {}}
        onToggleSameFolder={() => {}}
      />
    );

    expect(screen.getByLabelText(/output folder path/i)).toHaveAttribute("readonly");
    expect(screen.getByText(/pick the destination with the button below/i)).toBeInTheDocument();
  });
  it("requires a separate output folder when source files come from multiple directories", () => {
    render(<FolderPicker inputFolder="/assets" outputFolder="/exports" sameFolder={false}
      forceSeparateOutput onBrowseInput={() => {}} onBrowseOutput={() => {}}
      onToggleSameFolder={() => {}} />);
    const checkbox = screen.getByRole("checkbox", { name: "Same as input" });
    expect(checkbox).toBeDisabled();
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole("button", { name: /choose output folder/i })).toBeEnabled();
    expect(screen.getByText(/files may come from different folders/i)).toBeInTheDocument();
  });
});
