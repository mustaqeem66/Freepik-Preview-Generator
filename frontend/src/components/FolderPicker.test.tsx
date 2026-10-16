import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { FolderPicker } from "./FolderPicker";

describe("FolderPicker Component", () => {
  it("renders input folder path and responds to click", () => {
    const handleBrowseInput = vi.fn();
    const handleBrowseOutput = vi.fn();
    const handleToggleSame = vi.fn();

    render(
      <FolderPicker
        inputFolder="/path/to/my/assets"
        outputFolder="/path/to/my/output"
        sameFolder={false}
        onBrowseInput={handleBrowseInput}
        onBrowseOutput={handleBrowseOutput}
        onToggleSameFolder={handleToggleSame}
      />
    );

    expect(screen.getByText("/path/to/my/assets")).toBeInTheDocument();
    expect(screen.getByText("/path/to/my/output")).toBeInTheDocument();

    const inputBtn = screen.getByRole("button", { name: /choose input folder/i });
    fireEvent.click(inputBtn);
    expect(handleBrowseInput).toHaveBeenCalledTimes(1);

    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(handleToggleSame).toHaveBeenCalledWith(true);
  });

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
    expect(screen.getByText("Saving alongside source")).toBeInTheDocument();
  });
});
