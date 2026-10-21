import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssetGallery } from "./AssetGallery";
import { FileList } from "./FileList";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import type { FileInfo } from "../types";

const makeFiles = (count: number): FileInfo[] => Array.from({ length: count }, (_, i) => ({
  name: `art-${i}.png`, path: `/art/${i}.png`, ext: "PNG", is_3d: false,
}));

afterEach(() => { vi.restoreAllMocks(); });

describe("Asset gallery", () => {
  it("mounts a bounded number of tiles at 100,000 assets", () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue(undefined);
    render(<AssetGallery files={makeFiles(100_000)} matchedIndices={null}
      activeIndex={0} onSelect={() => {}} height={260} enabled={false}/>);
    const tiles = screen.getAllByTestId("gallery-tile");
    expect(tiles.length).toBeGreaterThan(0);
    expect(tiles.length).toBeLessThanOrEqual(16);
    expect(screen.getByTestId("asset-gallery").getAttribute("aria-rowcount")).toBe("50000");
    expect(tiles[0].getAttribute("aria-selected")).toBe("true");
  });

  it("preserves original indices under filename filtering", () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue(undefined);
    const selected = vi.fn();
    render(<AssetGallery files={makeFiles(120)} matchedIndices={[18, 21, 55]}
      activeIndex={18} onSelect={selected} height={260} enabled={false}/>);
    const tiles = screen.getAllByTestId("gallery-tile");
    fireEvent.click(tiles[1]);
    expect(selected).toHaveBeenCalledWith(21);
    fireEvent.keyDown(screen.getByTestId("asset-gallery"), { key: "ArrowDown" });
    expect(selected).toHaveBeenLastCalledWith(55);
  });

  it("requests only the visible files and displays event-driven thumbnails", async () => {
    const requested: string[][] = [];
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({
      request_thumbnails: vi.fn(async (paths: string[]) => {
        requested.push(paths);
        return { ok: true, value: {}, error: null };
      }),
    } as never);
    render(<AssetGallery files={makeFiles(20000)} matchedIndices={null}
      activeIndex={0} onSelect={() => {}} height={260} enabled />);
    await waitFor(() => expect(requested.length).toBeGreaterThan(0));
    expect(requested[0].length).toBeLessThanOrEqual(16);
    expect(requested[0].length).toBeLessThan(20000);
    bridgeEvents.emit("thumbnail.ready", {
      path: "/art/0.png", url: "http://127.0.0.1:4567/token/1.jpg",
    });
    await waitFor(() => expect(screen.getByRole("img", { hidden: true }).getAttribute("src"))
      .toBe("http://127.0.0.1:4567/token/1.jpg"));
  });

  it("keeps searching and selection when switching between list and gallery", () => {
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue(undefined);
    const selected = vi.fn();
    render(<FileList files={makeFiles(80)} activeIndex={0} onSelect={selected}
      height={260} enableThumbnails={false}/>);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "art-55" } });
    fireEvent.click(screen.getByRole("button", { name: "Gallery view" }));
    expect(screen.getAllByTestId("gallery-tile")).toHaveLength(1);
    fireEvent.click(screen.getByTestId("gallery-tile"));
    expect(selected).toHaveBeenCalledWith(55);
    fireEvent.click(screen.getByRole("button", { name: "List view" }));
    expect(screen.getAllByTestId("file-row")).toHaveLength(1);
    expect(screen.getByRole("searchbox")).toHaveProperty("value", "art-55");
  });

  it("does not show thumbnails for a disabled renderer", () => {
    const request = vi.fn();
    vi.spyOn(ApiBridge, "getApi").mockResolvedValue({ request_thumbnails: request } as never);
    render(<AssetGallery files={makeFiles(50)} matchedIndices={null}
      activeIndex={0} onSelect={() => {}} height={260} enabled={false}/>);
    expect(screen.getAllByTestId("gallery-tile").length).toBeLessThanOrEqual(16);
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });
});
