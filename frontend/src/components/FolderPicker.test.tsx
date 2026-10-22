import { describe, it, expect, vi } from "vitest";

import { fireEvent, render, screen } from "@testing-library/react";
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
  it("distinguishes the folder-only dialog from the visible file selector", () => {
    const chooseFolder = vi.fn();
    const browseFiles = vi.fn();
    render(<FolderPicker inputFolder="" outputFolder="" sameFolder={false}
      onBrowseInput={chooseFolder} onBrowseFiles={browseFiles}
      onBrowseOutput={() => {}} onToggleSameFolder={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose Folder" }));
    expect(chooseFolder).toHaveBeenCalledOnce();
    expect(browseFiles).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Browse Files…" }));
    expect(browseFiles).toHaveBeenCalledOnce();
  });

  it("does not render the removed source and destination helper copy", () => {
    render(<FolderPicker inputFolder="" outputFolder="" sameFolder={false}
      onBrowseInput={() => {}} onBrowseFiles={() => {}}
      onBrowseOutput={() => {}} onToggleSameFolder={() => {}} />);
    expect(screen.queryByText(/may hide files/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/allowed to write there/i)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Output folder path" })).toBeInTheDocument();
  });

  it("disables both source selectors while a native picker is busy", () => {
    render(<FolderPicker inputFolder="" outputFolder="" sameFolder={false} disabled
      onBrowseInput={() => {}} onBrowseFiles={() => {}}
      onBrowseOutput={() => {}} onToggleSameFolder={() => {}} />);
    expect(screen.getByRole("button", { name: "Choose Folder" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Browse Files…" })).toBeDisabled();
  });

});
