import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { HelpMenu } from "./HelpMenu";

describe("HelpMenu", () => {
  it("opens an accessible dialog, moves focus, and restores focus on Escape", () => {
    render(<HelpMenu onOpenDiagnostics={() => {}} />);
    const toggle = screen.getByRole("button", { name: /help and diagnostics/i });
    fireEvent.click(toggle);

    const dialog = screen.getByRole("dialog", { name: /help and diagnostics/i });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /close help/i })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  it("closes on an outside pointer press and runs the diagnostics action", () => {
    const onOpenDiagnostics = vi.fn();
    render(<HelpMenu onOpenDiagnostics={onOpenDiagnostics} />);
    const toggle = screen.getByRole("button", { name: /help and diagnostics/i });

    fireEvent.click(toggle);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /open diagnostics folder/i }));
    expect(onOpenDiagnostics).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
