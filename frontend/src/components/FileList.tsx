import { memo, useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { assetId, type FileInfo } from "../types";
import { useVirtualList } from "../hooks/useVirtualList";

export const FILE_ROW_HEIGHT = 34;

interface FileRowProps {
  file: FileInfo;
  index: number;
  position: number;
  active: boolean;
  top: number;
  onSelect: (index: number) => void;
  filesLength: number;
}
const FileRow = memo(function FileRow({ file, index, position, active, top, onSelect, filesLength }: FileRowProps) {
  return (
    <div
      id={assetId(file)}
      role="option"
      aria-selected={active}
      aria-rowindex={position + 1}
      aria-posinset={position + 1}
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
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }} title={file.name}>{file.name}</span>
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
 * Search is an index projection over the original source list, so selecting a
 * result never silently changes the export/preview target index.
 * Empty queries allocate no 100k-item projection, keeping the base list fast.
 */
export function FileList({ files, activeIndex, onSelect, height = 320 }: FileListProps) {
  const [query, setQuery] = useState("");
  const matchedIndices = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return null;
    const matches: number[] = [];
    for (let i = 0; i < files.length; i++) {
      if (files[i].name.toLocaleLowerCase().includes(normalized)) matches.push(i);
    }
    return matches;
  }, [files, query]);

  const count = matchedIndices?.length ?? files.length;
  const selectedPosition = matchedIndices ? matchedIndices.indexOf(activeIndex) : activeIndex;
  const originalIndexAt = useCallback((position: number) =>
    matchedIndices ? matchedIndices[position] : position, [matchedIndices]);
  const { containerRef, onScroll, virtualWindow } = useVirtualList({
    count, rowHeight: FILE_ROW_HEIGHT, viewportHeight: height,
  });
  const { start, end, totalHeight } = virtualWindow;
  const rows = useMemo(() => {
    const positions: number[] = [];
    for (let i = start; i < end; i++) positions.push(i);
    // The active-descendant element must exist even if the virtualizer has not
    // caught up with a keyboard jump / filtered selection.
    if (selectedPosition >= 0 && selectedPosition < count &&
        (selectedPosition < start || selectedPosition >= end)) positions.push(selectedPosition);

    return positions.map((position) => {
      const index = originalIndexAt(position);
      const file = files[index];
      if (!file) return null;
      return <FileRow key={assetId(file)} file={file} index={index} position={position}
        active={index === activeIndex} top={position * FILE_ROW_HEIGHT}
        onSelect={onSelect} filesLength={count} />;
    });
  }, [files, start, end, selectedPosition, count, originalIndexAt, activeIndex, onSelect]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || selectedPosition < 0 || selectedPosition >= count) return;
    const rowTop = selectedPosition * FILE_ROW_HEIGHT;
    const rowBottom = rowTop + FILE_ROW_HEIGHT;
    const scrollBottom = container.scrollTop + height;
    if (rowTop < container.scrollTop) container.scrollTop = rowTop;
    else if (rowBottom > scrollBottom) container.scrollTop = rowBottom - height;
  }, [selectedPosition, count, height, containerRef]);

  const pageSize = Math.max(1, Math.floor(height / FILE_ROW_HEIGHT));
  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (count === 0) return;
    const position = selectedPosition < 0 ? 0 : selectedPosition;
    let next: number;
    switch (event.key) {
      case "ArrowDown": next = Math.min(count - 1, position + (selectedPosition < 0 ? 0 : 1)); break;
      case "ArrowUp": next = Math.max(0, position - 1); break;
      case "PageDown": next = Math.min(count - 1, position + pageSize); break;
      case "PageUp": next = Math.max(0, position - pageSize); break;
      case "Home": next = 0; break;
      case "End": next = count - 1; break;
      default: return;
    }
    event.preventDefault();
    onSelect(originalIndexAt(next));
  }, [count, selectedPosition, pageSize, originalIndexAt, onSelect]);

  return (
    <div className="asset-list-group">
      <div className="asset-search-row">
        <input type="search" className="asset-search" aria-label="Search assets by filename"
          placeholder="Search assets…" value={query} onChange={(event) => setQuery(event.target.value)} />
        <span className="asset-search-count" role="status" aria-live="polite">
          {matchedIndices ? `${count} / ${files.length}` : `${files.length} assets`}
        </span>
      </div>
      <div
        ref={containerRef}
        role="listbox"
        aria-label="Asset list"
        aria-rowcount={count}
        aria-activedescendant={selectedPosition >= 0 && selectedPosition < count && files[activeIndex]
          ? assetId(files[activeIndex]) : undefined}
        data-testid="file-list"
        tabIndex={0}
        style={{ height, overflowY: "auto", overflowX: "hidden", position: "relative", flexShrink: 0 }}
        onScroll={onScroll}
        onKeyDown={handleKeyDown}
      >
        {count === 0 ? <div className="asset-no-matches" role="status">No matching assets. Clear the search to see all files.</div> :
          <div style={{ height: totalHeight, position: "relative" }}>
            <div style={{ position: "absolute", top: 0, left: 0, right: 0 }}>{rows}</div>
          </div>}
      </div>
    </div>
  );
}
