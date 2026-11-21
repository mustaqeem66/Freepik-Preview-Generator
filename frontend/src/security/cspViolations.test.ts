import { describe, expect, it, vi } from "vitest";
import {
  normaliseViolation,
  watchCspViolations,
} from "./cspViolations";

function violationEvent(fields: Record<string, unknown>): Event {
  const event = new Event("securitypolicyviolation");
  Object.assign(event, fields);
  return event;
}

describe("normaliseViolation", () => {
  it("keeps every field the engine supplies", () => {
    const result = normaliseViolation({
      effectiveDirective: "script-src",
      blockedURI: "https://example.invalid/x.js",
      violatedDirective: "script-src 'self'",
      resourceType: "script",
      sourceFile: "index.html",
      lineNumber: 3,
    } as never);

    expect(result).toEqual({
      effectiveDirective: "script-src",
      blockedURI: "https://example.invalid/x.js",
      violatedDirective: "script-src 'self'",
      resourceType: "script",
      sourceFile: "index.html",
      lineNumber: 3,
    });
  });

  it("substitutes empty strings when the engine omits fields", () => {
    const result = normaliseViolation({} as never);

    expect(result.effectiveDirective).toBe("");
    expect(result.blockedURI).toBe("");
    expect(result.violatedDirective).toBe("");
    expect(result.resourceType).toBe("");
    expect(result).not.toHaveProperty("sourceFile");
    expect(result).not.toHaveProperty("lineNumber");
  });

  it("still reports a violation that carries no detail at all", () => {
    // The fact that something was blocked is the fact the gate cares about.
    expect(normaliseViolation({} as never).resourceType).toBe("");
  });
});

describe("watchCspViolations", () => {
  it("forwards violations to the sink", async () => {
    const sink = vi.fn();
    const stop = watchCspViolations(sink);

    document.dispatchEvent(
      violationEvent({
        effectiveDirective: "connect-src",
        blockedURI: "https://example.invalid/beacon",
        resourceType: "xmlhttprequest",
      }),
    );
    await vi.waitFor(() => expect(sink).toHaveBeenCalledTimes(1));

    expect(sink.mock.calls[0][0]).toEqual([
      {
        effectiveDirective: "connect-src",
        blockedURI: "https://example.invalid/beacon",
        violatedDirective: "",
        resourceType: "xmlhttprequest",
      },
    ]);
    stop();
  });

  it("drains violations received during an in-flight bridge call", async () => {
    let finishFirst!: () => void;
    const first = new Promise<void>((resolve) => { finishFirst = resolve; });
    const sink = vi.fn().mockReturnValueOnce(first);
    const stop = watchCspViolations(sink);
    try {
      document.dispatchEvent(violationEvent({ blockedURI: "inline" }));
      document.dispatchEvent(violationEvent({ blockedURI: "blob" }));
      finishFirst();

      await vi.waitFor(() => expect(sink).toHaveBeenCalledTimes(2));
      expect(sink.mock.calls[1][0]).toMatchObject([{ blockedURI: "blob" }]);
    } finally {
      stop();
    }
  });

  it("stops delivering once the watcher is disposed", async () => {
    const sink = vi.fn();
    const stop = watchCspViolations(sink);
    stop();

    document.dispatchEvent(violationEvent({ blockedURI: "https://example.invalid/x" }));
    // The watcher batches and flushes asynchronously, so give the flush a
    // chance to run before asserting that nothing was delivered. Awaiting the
    // microtask queue is enough: the sink call is scheduled, not timed.
    await Promise.resolve();
    await Promise.resolve();

    expect(sink).not.toHaveBeenCalled();
  });

  it("does not break the app when the sink throws", async () => {
    const sink = vi.fn(() => {
      throw new Error("bridge is gone");
    });
    const stop = watchCspViolations(sink);

    document.dispatchEvent(violationEvent({ blockedURI: "https://example.invalid/x" }));
    await vi.waitFor(() => expect(sink).toHaveBeenCalledTimes(1));

    // The listener must survive a failing sink, otherwise the first transient
    // bridge error would silently disable violation reporting for the session.
    document.dispatchEvent(violationEvent({ blockedURI: "https://example.invalid/y" }));
    await vi.waitFor(() => expect(sink).toHaveBeenCalledTimes(2));
    stop();
  });
});
