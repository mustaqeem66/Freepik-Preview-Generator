import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import type { RefObject } from "react";
import { preventPaneSmoothScroll, shouldSmoothPaneMotion, useLenisPane } from "./useLenisPane";

const createLenis = vi.hoisted(() => vi.fn(() => ({ destroy: vi.fn() })));
vi.mock("lenis", () => ({ default: createLenis }));

function Pane() {
  const ref = useLenisPane();
  return <div ref={ref} data-testid="scroll-viewport"><div>Content</div></div>;
}

afterEach(() => {
  vi.restoreAllMocks();
  createLenis.mockClear();
});

describe("Lenis native desktop pane integration", () => {
  it("smooths only the local pane, not the window, and destroys on unmount", () => {
    const listeners: Array<(event: MediaQueryListEvent) => void> = [];
    const query = {
      matches: false,
      addEventListener: (_name: string, handler: (event: MediaQueryListEvent) => void) => listeners.push(handler),
      removeEventListener: vi.fn(),
    };
    vi.stubGlobal("matchMedia", vi.fn(() => query));
    const ui = render(<Pane />);
    expect(createLenis).toHaveBeenCalledTimes(1);
    const options = createLenis.mock.calls[0][0] as {
      wrapper: HTMLElement; content: HTMLElement; autoRaf: boolean; syncTouch: boolean;
      prevent: (node: HTMLElement) => boolean;
    };
    expect(options.wrapper).toBe(screen.getByTestId("scroll-viewport"));
    expect(options.content.textContent).toBe("Content");
    expect(options.autoRaf).toBe(true);
    expect(options.syncTouch).toBe(false);
    expect(options.prevent(document.createElement("input"))).toBe(true);
    const instance = createLenis.mock.results[0].value;
    ui.unmount();
    expect(instance.destroy).toHaveBeenCalledOnce();
    expect(query.removeEventListener).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("honors reduced-motion and reconfigures when preference changes", () => {
    let onChange: (() => void) | undefined;
    const preference = {
      matches: true,
      addEventListener: (_event: string, callback: () => void) => { onChange = callback; },
      removeEventListener: vi.fn(),
    };
    vi.stubGlobal("matchMedia", vi.fn(() => preference));
    const ui = render(<Pane />);
    expect(createLenis).not.toHaveBeenCalled();
    act(() => { preference.matches = false; onChange?.(); });
    expect(createLenis).toHaveBeenCalledTimes(1);
    const instance = createLenis.mock.results[0].value;
    act(() => { preference.matches = true; onChange?.(); });
    expect(instance.destroy).toHaveBeenCalledOnce();
    ui.unmount();
    vi.unstubAllGlobals();
  });

  it("leaves dialogs, file lists, and form fields to native scrolling", () => {
    expect(shouldSmoothPaneMotion(true)).toBe(false);
    expect(shouldSmoothPaneMotion(false)).toBe(true);
    const region = document.createElement("div");
    region.innerHTML = '<div role="listbox"><div class="row"></div></div>';
    expect(preventPaneSmoothScroll(region.querySelector(".row") as HTMLElement)).toBe(true);
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    expect(preventPaneSmoothScroll(dialog)).toBe(true);
    expect(preventPaneSmoothScroll(document.createElement("input"))).toBe(true);
    expect(preventPaneSmoothScroll(document.createElement("textarea"))).toBe(true);
    expect(preventPaneSmoothScroll(document.createElement("div"))).toBe(false);
  });
});
