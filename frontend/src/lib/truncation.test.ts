import { describe, expect, it } from "vitest";
import { formatTruncationReasons } from "./truncation";

describe("formatTruncationReasons", () => {
  it("maps backend codes to human labels", () => {
    expect(formatTruncationReasons(["maximum_files"])).toBe("file limit reached");
    expect(formatTruncationReasons(["permission_denied", "maximum_time"])).toBe(
      "some folders could not be read; time limit reached"
    );
  });

  it("keeps unknown codes readable instead of leaking underscores", () => {
    expect(formatTruncationReasons(["future_reason"])).toBe("future reason");
  });

  it("uses the fallback when no reason was reported", () => {
    expect(formatTruncationReasons([])).toBe("safety limit");
    expect(formatTruncationReasons([], "a safety limit")).toBe("a safety limit");
  });
});
