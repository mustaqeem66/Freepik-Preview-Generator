import { memo, useCallback, useEffect, useMemo, type KeyboardEvent } from "react";
import { assetId, FileInfo } from "../types";
import { useVirtualList } from "../hooks/useVirtualList";

export const FILE_ROW_HEIGHT = 34;

interface FileRowProps {
  file: FileInfo;
  index: number;
  active: boolean;
  top: number;
  onSelect: (index: number) => void;
  filesLength: number;
}
const FileRow = memo(function FileRow({ file, index, active, top, onSelect, filesLength }: FileRowProps) {
  return (
    <div
      id={assetId(file)}
      role="option"
      aria-selected={active}
      aria-rowindex={index + 1}
      aria-posinset={index + 1}
      aria-setsize={filesLength}
      data-testid="file-row"
      data-asset-id={assetId(file)}
      onClick={() => onSelect(index)}
      style={{
        position: "absolute",
        top,
        left: 0,
        right: 0,
        height: FILE_ROW_HEIGHT,
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "0 10px",
        cursor: "pointer",
        background: active ? "var(--chip-bg)" : "transparent",
        color: active ? "var(--accent)" : "inherit",
        fontSize: "12px",
        fontWeight: active ? 700 : 500,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        boxSizing: "border-box",
      }}
    >
      <span style={{ opacity: 0.6, flex: "0 0 40px" }}>{file.ext}</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{file.name}</span>
    </div>
  );
});

interface FileListProps {
  files: FileInfo[];
  activeIndex: number;
  onSelect: (index: number) => void;
  height?: number;
}

/**
 * Virtualized asset list. Only the visible slice is mounted, keyed by a stable
 * asset id (``file.path``) rather than array position, so scrolling, filtering,
 * selection, and keyboard navigation stay O(viewport) for arbitrarily large
 * batches.
 */
export function FileList({ files, activeIndex, onSelect, height = 320 }: FileListProps) {
  const { containerRef, onScroll, virtualWindow } = useVirtualList({
    count: files.length,
    rowHeight: FILE_ROW_HEIGHT,
    viewportHeight: height,
  });

  const { start, end, totalHeight } = virtualWindow;

  const rows = useMemo(() => {
    const visible = [];
    for (let i = start; i < end; i++) {
      const file = files[i];
      if (!file) continue;
      visible.push(
        <FileRow
          key={assetId(file)}
          file={file}
          index={i}
          active={i === activeIndex}
          top={i * FILE_ROW_HEIGHT}
          onSelect={onSelect}
          filesLength={files.length}
        />
      );
    }
    return visible;
  }, [files, start, end, activeIndex, onSelect]);

  // Auto-scroll container to keep the active item in view on selection or rescanning
  useEffect(() => {
    const container = containerRef.current;
    if (!container || activeIndex < 0 || activeIndex >= files.length) return;
    const rowTop = activeIndex * FILE_ROW_HEIGHT;
    const rowBottom = rowTop + FILE_ROW_HEIGHT;
    const scrollTop = container.scrollTop;
    const scrollBottom = scrollTop + height;
    if (rowTop < scrollTop) {
      container.scrollTop = rowTop;
    } else if (rowBottom > scrollBottom) {
      container.scrollTop = rowBottom - height;
    }
  }, [activeIndex, files.length, height, containerRef]);

  const pageSize = Math.max(1, Math.floor(height / FILE_ROW_HEIGHT));

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const last = files.length - 1;
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          onSelect(Math.min(last, activeIndex + 1));
          break;
        case "ArrowUp":
          event.preventDefault();
          onSelect(Math.max(0, activeIndex - 1));
          break;
        case "PageDown":
          event.preventDefault();
          onSelect(Math.min(last, activeIndex + pageSize));
          break;
        case "PageUp":
          event.preventDefault();
          onSelect(Math.max(0, activeIndex - pageSize));
          break;
        case "Home":
          event.preventDefault();
          onSelect(0);
          break;
        case "End":
          event.preventDefault();
          onSelect(last);
          break;
        default:
          break;
      }
    },
    [files.length, activeIndex, pageSize, onSelect]
  );

  return (
    <div
      ref={containerRef}
      role="listbox"
      aria-label="Asset list"
      aria-rowcount={files.length}
      aria-activedescendant={files[activeIndex] ? assetId(files[activeIndex]) : undefined}
      data-testid="file-list"
      tabIndex={0}
      style={{ height, overflowY: "auto", overflowX: "hidden", position: "relative", flexShrink: 0 }}
      onScroll={onScroll}
      onKeyDown={handleKeyDown}
    >
      <div style={{ height: totalHeight, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0 }}>{rows}</div>
      </div>
    </div>
  );
}
