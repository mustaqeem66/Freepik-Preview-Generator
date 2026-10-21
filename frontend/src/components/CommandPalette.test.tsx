import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CommandPalette, findCommands, type StudioCommand } from "./CommandPalette";

const actions = (fn = vi.fn()): StudioCommand[] => [
  { id: "source", title: "Choose source", group: "Library", keywords: "browse", action: fn },
  { id: "export", title: "Export JPG", group: "Export", disabled: true, action: vi.fn() },
  { id: "theme", title: "Switch theme", group: "View", action: vi.fn() },
];
describe("CommandPalette", () => {
  it("filters by labels, groups and keywords", () => {
    expect(findCommands(actions(), "BROWSE").map((x) => x.id)).toEqual(["source"]);
    expect(findCommands(actions(), "view").map((x) => x.id)).toEqual(["theme"]);
  });
  it("provides a modal and focuses the query", () => {
    render(<CommandPalette open actions={actions()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: "Quick actions" }).getAttribute("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Search actions" }));
    expect(screen.getByRole("option", { name: /Export JPG/ }).hasAttribute("disabled")).toBe(true);
  });
  it("uses arrows/Enter and skips disabled commands", () => {
    const run = vi.fn(), close = vi.fn();
    const options = actions(); options[2].action = run;
    render(<CommandPalette open actions={options} onClose={close}/>);
    const input = screen.getByRole("combobox");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /Switch theme/ }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(close).toHaveBeenCalledOnce();
    expect(run).toHaveBeenCalledOnce();
  });
  it("blocks a disabled-only result and supports unmatched state", () => {
    const close = vi.fn();
    render(<CommandPalette open actions={actions()} onClose={close}/>);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "export" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(close).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "NOTHING_MATCHES_123" } });
    expect(screen.getByText("No matching actions.")).toBeTruthy();
  });
  it("Escape closes and restores the previous focused element", () => {
    const trigger = document.createElement("button"); document.body.appendChild(trigger); trigger.focus();
    const close = vi.fn();
    const { rerender, unmount } = render(<CommandPalette open actions={actions()} onClose={close}/>);
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
    rerender(<CommandPalette open={false} actions={actions()} onClose={close}/>);
    expect(document.activeElement).toBe(trigger);
    unmount(); trigger.remove();
  });
});
