import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ErrorNotice, NoticeMessage } from "./ErrorNotice";

describe("ErrorNotice Component", () => {
  it("renders error and warning messages correctly", () => {
    const notices: NoticeMessage[] = [
      { id: "1", type: "error", message: "Folder Scan Failed", details: "Permission denied" },
      { id: "2", type: "warning", message: "Output Folder Missing" },
    ];
    const onDismiss = vi.fn();

    render(<ErrorNotice notices={notices} onDismiss={onDismiss} />);

    expect(screen.getByText("Folder Scan Failed")).toBeInTheDocument();
    expect(screen.getByText(/Permission denied/)).toBeInTheDocument();
    expect(screen.getByText("Output Folder Missing")).toBeInTheDocument();

    const dismissBtns = screen.getAllByTitle("Dismiss");
    expect(dismissBtns).toHaveLength(2);
    fireEvent.click(dismissBtns[0]!);
    expect(onDismiss).toHaveBeenCalledWith("1");
  });

  it("renders nothing when notices array is empty", () => {
    const { container } = render(<ErrorNotice notices={[]} onDismiss={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});
