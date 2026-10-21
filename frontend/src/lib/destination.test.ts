import { describe, expect, it } from "vitest";

import { resolveDestination } from "./destination";

describe("resolveDestination", () => {
  it("uses the source folder when same-folder is enabled", () => {
    expect(resolveDestination({
      inputFolder: "/art", outputFolder: "/exports", sameFolder: true,
    })).toBe("/art");
  });

  it("uses the chosen output folder when same-folder is disabled", () => {
    expect(resolveDestination({
      inputFolder: "/art", outputFolder: "/exports", sameFolder: false,
    })).toBe("/exports");
  });

  it("returns empty when the selected destination is missing", () => {
    expect(resolveDestination({
      inputFolder: "/art", outputFolder: "", sameFolder: false,
    })).toBe("");
    expect(resolveDestination({
      inputFolder: "", outputFolder: "/exports", sameFolder: true,
    })).toBe("");
  });

  it("ignores whitespace-only paths", () => {
    expect(resolveDestination({
      inputFolder: "/art", outputFolder: "   ", sameFolder: false,
    })).toBe("");
  });
});
