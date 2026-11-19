import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { FileImage, ImageOff } from "lucide-react";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import { useVirtualList } from "../hooks/useVirtualList";
import { assetId, type FileInfo, type PyWebViewApi } from "../types";
import "./assetGallery.css";

export const GALLERY_COLUMNS = 2;
export const GALLERY_ROW_HEIGHT = 130;
const MAX_VISIBLE = 16;

function keepVisible(old: Record<string, string>, paths: Iterable<string>): Record<string, string> {
  const next: Record<string, string> = {};
  for (const path of paths) if (old[path]) next[path] = old[path];
  const keys = Object.keys(old);
  // Keep React state stable when the visible thumbnail set did not change.
  return keys.length === Object.keys(next).length && keys.every((key) => next[key] === old[key])
    ? old : next;
}

function mergeVisible(
  old: Record<string, string>, paths: Iterable<string>, incoming: Record<string, string>
): Record<string, string> {
  const visible = keepVisible(old, paths);
  let next = visible;
  for (const path of paths) {
    const url = incoming[path];
    // Only accept thumbnails for the requested visible set.
    if (url && next[path] !== url) {
      if (next === visible) next = { ...visible };
      next[path] = url;
    }
  }
  return next;
}

interface Props {
  files: FileInfo[];
  matchedIndices: number[] | null;
  activeIndex: number;
  height: number;
  onSelect: (index: number) => void;
  enabled: boolean;
}

export function AssetGallery({ files, matchedIndices, activeIndex, height, onSelect, enabled }: Props) {
  const count = matchedIndices?.length ?? files.length;
  const positionAt = (position: number) => matchedIndices ? matchedIndices[position] : position;
  const activePosition = matchedIndices ? matchedIndices.indexOf(activeIndex) : activeIndex;
  const rowsCount = Math.ceil(count / GALLERY_COLUMNS);
  const { containerRef, onScroll, virtualWindow } = useVirtualList({
    count: rowsCount, rowHeight: GALLERY_ROW_HEIGHT, viewportHeight: height, overscan: 1,
  });
  const { start, end, totalHeight } = virtualWindow;
  const [images, setImages] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const imagesRef = useRef(images);
  const failedRef = useRef(failed);
  const currentlyVisible = useMemo(() => {
    const indices: number[] = [];
    for (let row = start; row < end; row++) {
      for (let col = 0; col < GALLERY_COLUMNS; col++) {
        const position = row * GALLERY_COLUMNS + col;
        if (position < count) indices.push(positionAt(position));
      }
    }
    return indices;
  }, [start, end, count, matchedIndices]);

  const paths = useMemo(() =>
    enabled ? currentlyVisible.slice(0, MAX_VISIBLE).map((i) => files[i]?.path).filter((p): p is string => !!p)
      : [], [enabled, currentlyVisible, files]);
  const pathsKey = JSON.stringify(paths);
  const wantedRef = useRef<Set<string>>(new Set());
  const apiRef = useRef<PyWebViewApi | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    const unReady = bridgeEvents.subscribe("thumbnail.ready", ({ path, url }) => {
      if (!wantedRef.current.has(path)) return;
      if (failedRef.current.has(path)) {
        const next = new Set(failedRef.current);
        next.delete(path);
        failedRef.current = next;
        setFailed(next);
      }
      if (imagesRef.current[path] !== url) {
        const next = { ...imagesRef.current, [path]: url };
        imagesRef.current = next;
        setImages(next);
      }
    });
    const unFailed = bridgeEvents.subscribe("thumbnail.failed", ({ path }) => {
      if (!wantedRef.current.has(path) || failedRef.current.has(path)) return;
      const next = new Set(failedRef.current);
      next.add(path);
      failedRef.current = next;
      setFailed(next);
    });
    return () => { unReady(); unFailed(); };
  }, []);

  useEffect(() => {
    const wanted: string[] = JSON.parse(pathsKey) as string[];
    wantedRef.current = new Set(wanted);
    const visibleImages = keepVisible(imagesRef.current, wanted);
    if (visibleImages !== imagesRef.current) {
      imagesRef.current = visibleImages;
      setImages(visibleImages);
    }
    const visibleFailed = new Set([...failedRef.current].filter((p) => wantedRef.current.has(p)));
    if (visibleFailed.size !== failedRef.current.size) {
      failedRef.current = visibleFailed;
      setFailed(visibleFailed);
    }
    const generation = ++generationRef.current;
    // Debounce fast wheel navigation. Only the latest visible set reaches Python.
    const timer = window.setTimeout(async () => {
      try {
        const api = await ApiBridge.getApi(250);
        if (generation !== generationRef.current || !api?.request_thumbnails) return;
        apiRef.current = api;
        const response = await api.request_thumbnails(wanted);
        if (generation !== generationRef.current || !response?.ok || !response.value) return;
        const cached = response.value;
        const next = mergeVisible(imagesRef.current, wanted, cached);
        if (next !== imagesRef.current) {
          imagesRef.current = next;
          setImages(next);
        }
      } catch {
        // Gallery falls back to format tiles while the backend is unavailable.
      }
    }, 120);
    return () => { window.clearTimeout(timer); generationRef.current++; };
  }, [pathsKey]);

  useEffect(() => {
    // Reconfirm currently visible tiles once a minute. The backend expires
    // cached handles before the preview server's age-based cleanup can evict them.
    const interval = window.setInterval(async () => {
      const wanted = [...wantedRef.current];
      const api = apiRef.current;
      if (!wanted.length || !api?.request_thumbnails) return;
      try {
        const result = await api.request_thumbnails(wanted);
        if (!result.ok || !result.value) return;
        const returned = result.value;
        const next = mergeVisible(imagesRef.current, wantedRef.current, returned);
        if (next !== imagesRef.current) {
          imagesRef.current = next;
          setImages(next);
        }
      } catch { /* The icon placeholder remains available offline. */ }
    }, 60_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => () => {
    wantedRef.current.clear();
    // Release pending work; session LRU stays bounded for reopening gallery.
    const task = apiRef.current?.request_thumbnails?.([]);
    void task?.catch(() => {});
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || activePosition < 0 || activePosition >= count) return;
    const top = Math.floor(activePosition / GALLERY_COLUMNS) * GALLERY_ROW_HEIGHT;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + GALLERY_ROW_HEIGHT > el.scrollTop + height) {
      el.scrollTop = top + GALLERY_ROW_HEIGHT - height;
    }
  }, [activePosition, count, height, containerRef]);

  const selectedRow = activePosition >= 0 ? Math.floor(activePosition / GALLERY_COLUMNS) : -1;
  const rows = [];
  for (let row = start; row < end; row++) rows.push(row);
  // Match existing list accessibility: the active option must be present even
  // when the user jumps directly to an offscreen asset.
  if (selectedRow >= 0 && (selectedRow < start || selectedRow >= end)) rows.push(selectedRow);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!count) return;
    const at = activePosition >= 0 ? activePosition : 0;
    const page = Math.max(1, Math.floor(height / GALLERY_ROW_HEIGHT)) * GALLERY_COLUMNS;
    let target;
    switch (event.key) {
      case "ArrowRight": target = Math.min(count - 1, at + 1); break;
      case "ArrowLeft": target = Math.max(0, at - 1); break;
      case "ArrowDown": target = Math.min(count - 1, at + GALLERY_COLUMNS); break;
      case "ArrowUp": target = Math.max(0, at - GALLERY_COLUMNS); break;
      case "PageDown": target = Math.min(count - 1, at + page); break;
      case "PageUp": target = Math.max(0, at - page); break;
      case "Home": target = 0; break;
      case "End": target = count - 1; break;
      default: return;
    }
    event.preventDefault();
    onSelect(positionAt(target));
  };

  return <div ref={containerRef} className="asset-gallery" role="listbox"
    aria-label="Asset gallery"
    aria-activedescendant={activePosition >= 0 && activePosition < count && files[activeIndex]
      ? assetId(files[activeIndex]) : undefined}
    data-testid="asset-gallery" tabIndex={0} onKeyDown={onKeyDown} onScroll={onScroll}
    style={{ height, overflowY: "auto", overflowX: "hidden", position: "relative" }}>
    {count === 0
      ? <div className="asset-no-matches" role="status">No matching assets. Clear your search.</div>
      : <div style={{ height: totalHeight, position: "relative" }}>
          {rows.map((row) => <div key={row} className="gallery-row"
            style={{ position: "absolute", left: 0, right: 0, top: row * GALLERY_ROW_HEIGHT,
              height: GALLERY_ROW_HEIGHT }}>
            {[0, 1].map((col) => {
              const position = row * GALLERY_COLUMNS + col;
              if (position >= count) return null;
              const originalIndex = positionAt(position);
              const file = files[originalIndex];
              if (!file) return null;
              const image = images[file.path];
              const imageFailed = failed.has(file.path);
              return <button key={assetId(file)} id={assetId(file)} type="button" role="option"
                aria-selected={originalIndex === activeIndex} aria-posinset={position + 1}
                aria-setsize={count} data-testid="gallery-tile" tabIndex={-1}
                title={file.name} onClick={() => onSelect(originalIndex)}
                className="gallery-tile" data-asset-id={assetId(file)}>
                <span className="gallery-art" aria-hidden="true">
                  {image && !imageFailed
                    ? <img src={image} loading="lazy" decoding="async"
                        onError={() => {
                          if (failedRef.current.has(file.path)) return;
                          const next = new Set(failedRef.current);
                          next.add(file.path);
                          failedRef.current = next;
                          setFailed(next);
                        }} alt="" />
                    : imageFailed ? <ImageOff size={23} strokeWidth={1.4}/> :
                      <FileImage size={23} strokeWidth={1.4}/>}
                </span>
                <span className="gallery-asset-name">{file.name}</span>
                <span className="gallery-asset-kind">{file.ext}</span>
              </button>;
            })}
          </div>)}
        </div>}
  </div>;
}
