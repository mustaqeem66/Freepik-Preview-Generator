import { useCallback, useEffect, useState } from "react";

/**
 * Opt-in canvas-only desktop workspace.
 * Does not persist the mode: every fresh launch reveals navigation and inspector.
 */
export function useStudioFocus() {
  const [isFocused, setIsFocused] = useState(false);
  const toggleFocus = useCallback(() => setIsFocused((value) => !value), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Do not steal Escape from a native HTML dialog or another modal.
      if (event.key === "Escape" && isFocused) {
        if (document.querySelector("dialog[open], [aria-modal='true']")) return;
        event.preventDefault();
        setIsFocused(false);
        return;
      }

      if (!event.altKey || !event.shiftKey || event.ctrlKey || event.metaKey ||
          event.key.toLowerCase() !== "f" || event.repeat || event.defaultPrevented) return;
      const target = event.target;
      if (target instanceof Element &&
          target.closest("input, textarea, select, [contenteditable='true'], [role='textbox'], dialog")) return;
      event.preventDefault();
      setIsFocused((value) => !value);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isFocused]);

  return { isFocused, toggleFocus };
}
