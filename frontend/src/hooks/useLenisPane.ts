import { useEffect, useRef } from "react";
import Lenis from "lenis";

/**
 * Lenis is restricted to each real pane, never the global window.
 *
 * This prevents animated wheel events from fighting independently virtualized
 * asset lists, the gallery, range-input drag gestures, or native file dialogs.
 * Reduced-motion users keep the browser's own scroll implementation.
 */
export function shouldSmoothPaneMotion(reducedMotion: boolean): boolean {
  return !reducedMotion;
}

export function preventPaneSmoothScroll(target: HTMLElement): boolean {
  return Boolean(target.closest(
    '[data-lenis-prevent], [role="listbox"], [role="dialog"], ' +
    'input, textarea, select, [role="slider"], [data-native-scroll]',
  ));
}

export function useLenisPane() {
  const paneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrapper = paneRef.current;
    const content = wrapper?.firstElementChild;
    if (!wrapper || !(content instanceof HTMLElement)) return;

    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let instance: Lenis | null = null;
    const configure = () => {
      instance?.destroy();
      instance = null;
      if (!shouldSmoothPaneMotion(preference?.matches ?? false)) return;
      instance = new Lenis({
        wrapper,
        content,
        autoRaf: true,
        smoothWheel: true,
        syncTouch: false,
        lerp: 0.16,
        wheelMultiplier: 0.85,
        overscroll: false,
        prevent: preventPaneSmoothScroll,
      });
    };
    configure();
    preference?.addEventListener?.("change", configure);
    return () => {
      preference?.removeEventListener?.("change", configure);
      instance?.destroy();
    };
  }, []);

  return paneRef;
}
