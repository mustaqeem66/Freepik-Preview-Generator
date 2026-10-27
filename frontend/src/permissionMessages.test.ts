import { describe, expect, it } from "vitest";
import { describeNativePickerFailure } from "./permissionMessages";

describe("native picker permission guidance", () => {
  it("does not recommend bypassing picker-grant security after a native dialog failure", () => {
    const message = describeNativePickerFailure(new Error("Dialog cancelled by operating system"));
    expect(message).toContain("Dialog cancelled");
    expect(message).toContain("native folder or Add Files picker");
    expect(message).toContain("Typing a path does not grant access");
    expect(message).not.toContain("paste the folder path instead");
  });

  it("handles unknown failures without suggesting a manual path", () => {
    expect(describeNativePickerFailure(null)).toMatch(/native file picker is unavailable/i);
    expect(describeNativePickerFailure({ cause: "x" })).toMatch(/Typing a path does not grant access/);
  });
});
