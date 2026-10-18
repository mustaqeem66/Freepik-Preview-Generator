import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FileList } from "./FileList";
import { FileInfo } from "../types";

function makeFiles(count: number): FileInfo[] {
  return Array.from({ length: count }, (_, i) => ({
    name: `asset-${i}.png`,
    path: `/assets/asset-${i}.png`,
    ext: "PNG",
    is_3d: false,
  }));
}

describe("FileList virtualization", () => {
  it("mounts only a small window of rows for a huge list", () => {
    const files = makeFiles(5000);
    render(<FileList files={files} activeIndex={0} onSelect={() => {}} height={200} />);

    const rows = screen.getAllByTestId("file-row");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThanOrEqual(13);
    expect(rows[0].getAttribute("data-asset-id")).toBe("/assets/asset-0.png");
  });

  it("keeps virtualization bounded at 100,000+ items", () => {
    const files = makeFiles(100_001);
    render(<FileList files={files} activeIndex={0} onSelect={() => {}} height={200} />);

    const rows = screen.getAllByTestId("file-row");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThanOrEqual(13);
    expect(screen.getByTestId("file-list")).toBeTruthy();
  });

  it("keys rows by stable asset id and selects by index", () => {
    const files = makeFiles(50);
    const onSelect = vi.fn();
    render(<FileList files={files} activeIndex={3} onSelect={onSelect} height={200} />);

    const rows = screen.getAllByTestId("file-row");
    expect(rows[3].getAttribute("aria-selected")).toBe("true");

    fireEvent.click(rows[5]);
    expect(onSelect).toHaveBeenCalledWith(5);
  });

  it("supports full keyboard navigation including PageUp, PageDown, Home, End", () => {
    const files = makeFiles(50);
    const onSelect = vi.fn();
    render(<FileList files={files} activeIndex={10} onSelect={onSelect} height={200} />);

    const list = screen.getByTestId("file-list");
    fireEvent.keyDown(list, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith(11);

    fireEvent.keyDown(list, { key: "ArrowUp" });
    expect(onSelect).toHaveBeenLastCalledWith(9);

    // Height 200 / 34 = 5 items per page
    fireEvent.keyDown(list, { key: "PageDown" });
    expect(onSelect).toHaveBeenLastCalledWith(15);

    fireEvent.keyDown(list, { key: "PageUp" });
    expect(onSelect).toHaveBeenLastCalledWith(5);

    fireEvent.keyDown(list, { key: "End" });
    expect(onSelect).toHaveBeenLastCalledWith(49);

    fireEvent.keyDown(list, { key: "Home" });
    expect(onSelect).toHaveBeenLastCalledWith(0);
  });

  it("provides screen-reader row count and active descendant metadata", () => {
    const files = makeFiles(50);
    render(<FileList files={files} activeIndex={2} onSelect={() => {}} height={200} />);

    const list = screen.getByTestId("file-list");
    expect(list.getAttribute("aria-rowcount")).toBe("50");
    expect(list.getAttribute("aria-activedescendant")).toBe("/assets/asset-2.png");

    const rows = screen.getAllByTestId("file-row");
    expect(rows[0].getAttribute("aria-rowindex")).toBe("1");
    expect(rows[0].getAttribute("aria-posinset")).toBe("1");
    expect(rows[2].getAttribute("aria-selected")).toBe("true");
    expect(rows[2].id).toBe("/assets/asset-2.png");
  });

  it("exposes aria-setsize and updates when active selection changes", () => {
    const files = makeFiles(100);
    const { rerender } = render(<FileList files={files} activeIndex={0} onSelect={() => {}} height={200} />);

    let rows = screen.getAllByTestId("file-row");
    expect(rows[0].getAttribute("aria-setsize")).toBe("100");
    expect(rows[0].getAttribute("aria-selected")).toBe("true");

    // Rerender with different active index
    rerender(<FileList files={files} activeIndex={4} onSelect={() => {}} height={200} />);
    const list = screen.getByTestId("file-list");
    expect(list.getAttribute("aria-activedescendant")).toBe("/assets/asset-4.png");

    rows = screen.getAllByTestId("file-row");
    expect(rows[4].getAttribute("aria-selected")).toBe("true");
    expect(rows[0].getAttribute("aria-selected")).toBe("false");
  });

  it("handles scroll to selected index when selection changes", () => {
    const files = makeFiles(200);
    const { rerender } = render(<FileList files={files} activeIndex={0} onSelect={() => {}} height={200} />);
    const list = screen.getByTestId("file-list");

    // Change activeIndex to item deep in list
    rerender(<FileList files={files} activeIndex={50} onSelect={() => {}} height={200} />);
    expect(list.getAttribute("aria-activedescendant")).toBe("/assets/asset-50.png");
  });
});
