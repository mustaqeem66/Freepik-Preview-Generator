import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { WebFallbackBridge, isWebFallbackApi } from "./webFallbackBridge";
import { SETTINGS_DEFAULTS } from "../generated/settingsContract";
import type { PreviewState } from "../types";

describe("unprivileged browser demo", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => {
    delete window.__onScanFinished;
    vi.restoreAllMocks();
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

  it("renders rectangular exports without stretching the sample artwork", async () => {
    const bridge = new WebFallbackBridge();
    const ctx = {
      fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      closePath: vi.fn(), fill: vi.fn(), fillText: vi.fn(), roundRect: vi.fn(),
      save: vi.fn(), translate: vi.fn(), restore: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as never);
    const access = bridge as unknown as {
      draw: (path: string, state: PreviewState, width: number,
        sourceOnly: boolean, height: number) => Promise<HTMLCanvasElement>;
    };
    const state = { ...SETTINGS_DEFAULTS, text: "" } as PreviewState;
    const canvas = await access.draw("browser-demo://samples/glass.png", state, 900, false, 450);
    expect([canvas.width, canvas.height]).toEqual([900, 450]);
    expect(ctx.translate).toHaveBeenCalledWith(225, 0);
    expect(ctx.restore).toHaveBeenCalledOnce();
  });

  it("downloads the independently requested width and height", async () => {
    const bridge = new WebFallbackBridge();
    const state = { ...SETTINGS_DEFAULTS, outputWidth: 1000, outputHeight: 500 } as PreviewState;
    const exposed = bridge as unknown as {
      render: (path: string, state: PreviewState, width: number,
        sourceOnly: boolean, height: number) => Promise<string>;
    };
    const renderSpy = vi.spyOn(exposed, "render").mockResolvedValue("blob:preview-demo");
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const response = await bridge.export_preview("browser-demo://samples/glass.png", state);
    expect(response.ok).toBe(true);
    expect(response.value).toMatchObject({ width: 1000, height: 500 });
    expect(renderSpy).toHaveBeenCalledWith(
      "browser-demo://samples/glass.png", state, 1000, false, 500,
    );
    expect(clickSpy).toHaveBeenCalledOnce();
  });

  it("sanitizes browser storage and never persists native file paths", async () => {
    localStorage.setItem("previewgen.browserDemo.v1", JSON.stringify({
      inputFolder: "/untrusted/input", outputFolder: "/private/output",
      logoPath: "/private/logo.svg", fontPath: "/private/font.otf",
      theme: "neon", solidColor: "red", outputWidth: 1_000_000,
      text: "Studio",
    }));
    const bridge = new WebFallbackBridge();
    const initial = (await bridge.get_initial_state()).value;
    expect(initial.inputFolder).toBe("browser-demo://samples");
    expect(initial.outputFolder).toBe("Browser Downloads");
    expect(initial.logoPath).toBe("");
    expect(initial.fontPath).toBe("");
    expect(initial.theme).toBe("light");
    expect(initial.solidColor).toBe("#FFFFFF");
    expect(initial.outputWidth).toBe(8192);
    expect(initial.text).toBe("Studio");

    const saved = await bridge.save_settings({
      ...SETTINGS_DEFAULTS,
      inputFolder: "/secret", outputFolder: "/secret", logoPath: "/logo.svg",
      fontPath: "/font.otf",
    } as PreviewState);
    expect(saved.ok).toBe(true);
    const stored = JSON.parse(localStorage.getItem("previewgen.browserDemo.v1") || "{}");
    expect(stored.inputFolder).toBeUndefined();
    expect(stored.outputFolder).toBeUndefined();
    expect(stored.logoPath).toBeUndefined();
    expect(stored.fontPath).toBeUndefined();
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
