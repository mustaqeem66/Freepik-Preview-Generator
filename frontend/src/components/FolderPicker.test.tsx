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
});
