import { useCallback, useMemo, useRef, useState } from "react";

export interface VirtualWindow {
  /** First rendered row index (inclusive). */
  start: number;
  /** Last rendered row index (exclusive). */
  end: number;
  /** Pixel offset of the first rendered row. */
  offsetY: number;
  /** Total scrollable height for every row. */
  totalHeight: number;
}

/**
 * Pure windowing math so it can be unit-tested without a DOM. Only the rows
 * intersecting the viewport (plus ``overscan``) are returned, which keeps
 * render time, reconciliation, and memory independent of the asset count.
 */
export function computeVirtualWindow(
  count: number,
  rowHeight: number,
  scrollTop: number,
  viewportHeight: number,
  overscan = 6
): VirtualWindow {
  if (count <= 0 || rowHeight <= 0 || viewportHeight <= 0) {
    return { start: 0, end: 0, offsetY: 0, totalHeight: 0 };
  }
  const totalHeight = count * rowHeight;
  const visibleRows = Math.max(1, Math.ceil(viewportHeight / rowHeight));
  const lastIndex = count - 1;
  // Clamp the first visible row so overscroll past the end never yields a
  // window where start > end.
  const firstVisible = Math.min(lastIndex, Math.floor(Math.max(0, scrollTop) / rowHeight));
  const start = Math.max(0, firstVisible - overscan);
  const end = Math.min(count, firstVisible + visibleRows + overscan);
  return { start, end, offsetY: start * rowHeight, totalHeight };
}

export interface UseVirtualListOptions {
  count: number;
  rowHeight: number;
  viewportHeight: number;
  overscan?: number;
}

export function useVirtualList({ count, rowHeight, viewportHeight, overscan = 6 }: UseVirtualListOptions) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  const virtualWindow = useMemo(
    () => computeVirtualWindow(count, rowHeight, scrollTop, viewportHeight, overscan),
    [count, rowHeight, scrollTop, viewportHeight, overscan]
  );

  return { containerRef, onScroll, virtualWindow, scrollTop };
}
