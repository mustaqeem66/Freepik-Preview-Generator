import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { WebFallbackBridge, isWebFallbackApi } from "./webFallbackBridge";

describe("unprivileged browser demo", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => {
    delete window.__onScanFinished;
    vi.useRealTimers();
  });

  it("starts with four synthetic files, without exposing arbitrary local paths", async () => {
    const bridge = new WebFallbackBridge();
    expect(isWebFallbackApi(bridge)).toBe(true);
    const state = await bridge.get_initial_state();
    expect(state.ok).toBe(true);
    expect(state.value.inputFolder).toBe("browser-demo://samples");
    expect(state.value.outputFolder).toBe("Browser Downloads");

    const finished = vi.fn();
    window.__onScanFinished = finished;
    const started = await bridge.start_scan("browser-demo://samples");
    expect(started.ok).toBe(true);
    await vi.runAllTimersAsync();
    expect(finished).toHaveBeenCalledOnce();
    const payload = finished.mock.calls[0][1];
    expect(payload.status).toBe("completed");
    expect(payload.files.map((entry: { name: string }) => entry.name)).toEqual([
      "Aurora-Badge-Icon.svg",
      "Orbital-Prism-Mesh.glb",
      "Inter-Display-Specimen.otf",
      "Glass-UI-Card.png",
    ]);
    expect(payload.files).toHaveLength(4);
  });

  it("never grants a guessed folder path or a native output filesystem", async () => {
    const bridge = new WebFallbackBridge();
    const forbidden = await bridge.start_scan("/private/home/secrets");
    expect(forbidden.ok).toBe(false);
    expect(forbidden.error).toBe("UNAUTHORIZED_INPUT_PATH");
    const folder = await bridge.open_folder("/private/home/secrets");
    expect(folder.ok).toBe(false);
    const batch = await bridge.start_batch("browser-demo://samples", "Browser Downloads", {} as never);
    expect(batch.ok).toBe(false);
    expect(batch.error).toMatch(/requires PreviewGen Desktop/);
  });

  it("reports cancellation as a terminal scan outcome", async () => {
    const bridge = new WebFallbackBridge();
    const finished = vi.fn();
    window.__onScanFinished = finished;
    const started = await bridge.start_scan("browser-demo://samples");
    expect(started.scanId).toBeDefined();
    await bridge.cancel_scan(started.scanId);
    await vi.runAllTimersAsync();
    expect(finished.mock.calls[0][1].status).toBe("cancelled");
    expect(finished.mock.calls[0][1].files).toEqual([]);
  });

  it("keeps browser settings local and does not restore filesystem grants", async () => {
    const bridge = new WebFallbackBridge();
    const initial = (await bridge.get_initial_state()).value;
    await bridge.save_settings({ ...initial, inputFolder: "/untrusted/path", text: "Custom" } as never);
    const reloaded = new WebFallbackBridge();
    const restored = (await reloaded.get_initial_state()).value;
    expect(restored.inputFolder).toBe("browser-demo://samples");
    expect(restored.text).toBe("Custom");
    expect((await reloaded.start_scan("/untrusted/path")).ok).toBe(false);
  });
});
