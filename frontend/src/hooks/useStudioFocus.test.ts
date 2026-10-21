import { describe, expect, it } from "vitest";
import { act, fireEvent, renderHook } from "@testing-library/react";
import { useStudioFocus } from "./useStudioFocus";

describe("useStudioFocus", () => {
  it("starts with visible panels and allows a reversible explicit toggle", () => {
    const { result } = renderHook(() => useStudioFocus());
    expect(result.current.isFocused).toBe(false);
    act(() => result.current.toggleFocus());
    expect(result.current.isFocused).toBe(true);
    act(() => result.current.toggleFocus());
    expect(result.current.isFocused).toBe(false);
  });

  it("supports Alt+Shift+F and Escape without leaving focus trapped", () => {
    const { result } = renderHook(() => useStudioFocus());
    fireEvent.keyDown(window, { key: "f", altKey: true, shiftKey: true });
    expect(result.current.isFocused).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(result.current.isFocused).toBe(false);
  });

  it("does not steal the shortcut from editable controls", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    const { result, unmount } = renderHook(() => useStudioFocus());
    try {
      fireEvent.keyDown(input, { key: "f", altKey: true, shiftKey: true });
      expect(result.current.isFocused).toBe(false);
    } finally {
      unmount();
      input.remove();
    }
  });

  it("preserves modal dialog Escape handling", () => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.appendChild(dialog);
    const { result, unmount } = renderHook(() => useStudioFocus());
    try {
      act(() => result.current.toggleFocus());
      fireEvent.keyDown(window, { key: "Escape" });
      expect(result.current.isFocused).toBe(true);
    } finally {
      unmount();
      dialog.remove();
    }
  });
});
