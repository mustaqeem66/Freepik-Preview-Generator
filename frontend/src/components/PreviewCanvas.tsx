import { useEffect, useRef, useState } from "react";
import { Image as ImageIcon, Loader2, Move3D, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import "./previewControls.css";
import { BeforeAfterComparison } from "./BeforeAfterComparison";

interface PreviewCanvasProps {
  previewUrl: string | null;
  isLoading: boolean;
  renderError: string | null;
  name: string;
  width: number;
  height: number;
  is3D?: boolean;
  yaw?: number;
  pitch?: number;
  onOrbit?: (yaw: number, pitch: number) => void;
  onChooseFolder?: () => void;
  canChooseFolder?: boolean;
  hasSourceFolder?: boolean;
  compareEnabled?: boolean;
  sourceUrl?: string | null;
  sourceLoading?: boolean;
  sourceError?: string | null;
  onExitCompare?: () => void;
}

export function PreviewCanvas({ previewUrl, isLoading, renderError, name, width, height,
  is3D = false, yaw = 45, pitch = 30, onOrbit, onChooseFolder,
  canChooseFolder = false, hasSourceFolder = false, compareEnabled = false,
  sourceUrl = null, sourceLoading = false, sourceError = null,
  onExitCompare }: PreviewCanvasProps) {
  const drag = useRef<
    | { kind: "orbit"; x: number; y: number; yaw: number; pitch: number }
    | { kind: "pan"; x: number; y: number; panX: number; panY: number }
    | null
  >(null);
  const [imageError, setImageError] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  useEffect(() => {
    setImageError(false);
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [previewUrl]);
  useEffect(() => {
    if (zoom <= 1) setPan({ x: 0, y: 0 });
  }, [zoom]);
  const orbit = (y: number, p: number) => onOrbit?.(((y % 360) + 360) % 360, Math.max(-85, Math.min(85, p)));
  const error = renderError || (imageError ? "The rendered image could not be loaded. Select the asset again to retry." : null);
  return <div className={`preview-canvas${is3D ? " orbit-canvas" : !compareEnabled && zoom > 1 ? " zoom-pan-canvas" : ""}`} aria-busy={isLoading}
    role="group" aria-label={is3D ? "3D preview. Drag to orbit; Shift and arrow keys adjust the camera." : "Live preview"}
    tabIndex={is3D ? 0 : undefined}
    onKeyDown={(e) => {
      if (!is3D || !e.shiftKey || !e.key.startsWith("Arrow")) return;
      e.preventDefault(); e.stopPropagation();
      orbit(yaw + (e.key === "ArrowRight" ? 5 : e.key === "ArrowLeft" ? -5 : 0),
        pitch + (e.key === "ArrowUp" ? 5 : e.key === "ArrowDown" ? -5 : 0));
    }}
    onPointerDown={(e) => {
      if (compareEnabled || !previewUrl || e.button !== 0 || (e.target instanceof Element &&
          e.target.closest(".preview-zoom-controls"))) return;
      if (is3D) drag.current = { kind: "orbit", x: e.clientX, y: e.clientY, yaw, pitch };
      else if (zoom > 1) drag.current = { kind: "pan", x: e.clientX, y: e.clientY,
        panX: pan.x, panY: pan.y };
      else return;
      e.currentTarget.setPointerCapture(e.pointerId);
    }}
    onPointerMove={(e) => {
      const start = drag.current;
      if (!start) return;
      if (start.kind === "orbit") orbit(start.yaw + (e.clientX - start.x) * 0.5,
        start.pitch - (e.clientY - start.y) * 0.5);
      else setPan({ x: start.panX + e.clientX - start.x, y: start.panY + e.clientY - start.y });
    }}
    onPointerUp={() => { drag.current = null; }}
    onPointerCancel={() => { drag.current = null; }}
    onLostPointerCapture={() => { drag.current = null; }}>
    {isLoading && <div className="rendering-indicator" role="status"><Loader2 size={15} className="animate-spin" />Rendering preview…</div>}
    {error && <div className="preview-error" role="alert"><strong>Preview unavailable</strong><p>{error}</p></div>}
    {!error && previewUrl && compareEnabled && sourceUrl && onExitCompare
      ? <BeforeAfterComparison sourceUrl={sourceUrl} previewUrl={previewUrl}
          name={name} onClose={onExitCompare} />
      : !error && previewUrl && <img src={previewUrl} alt={name || "Preview"} draggable={false}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          onError={() => setImageError(true)} />}
    {compareEnabled && sourceLoading && !sourceUrl && <span className="comparison-status" role="status">
      Preparing source visualization…
    </span>}
    {compareEnabled && sourceError && !sourceUrl && <span className="comparison-status comparison-failure" role="alert">
      {sourceError}
    </span>}
    {!error && !previewUrl && !isLoading && <div className="empty-canvas">
      <span className="empty-canvas-icon"><ImageIcon size={32} strokeWidth={1.25} /></span>
      <h2>{hasSourceFolder ? "No preview selected" : "Your artwork, ready to present"}</h2>
      <p>{hasSourceFolder
        ? "Select an asset from the library to inspect the preview."
        : "Choose a source folder, preview your artwork, then generate JPGs."}</p>
      {!hasSourceFolder && canChooseFolder && onChooseFolder &&
        <button className="button primary empty-canvas-action" type="button" onClick={onChooseFolder}>Choose Input Folder</button>}
      <span className="empty-formats">Raster · Vector · 3D · Creator files</span>
    </div>}
    {!error && previewUrl && !compareEnabled && <div className="preview-zoom-controls" role="group"
      aria-label="Preview magnification" onPointerDown={(event) => event.stopPropagation()}>
      <button type="button" aria-label="Zoom out" title="Zoom out"
        disabled={zoom <= 1} onClick={() => setZoom((value) => Math.max(1, value - 0.25))}><ZoomOut size={15} /></button>
      <span className="preview-zoom-level" aria-live="polite">{Math.round(zoom * 100)}% of fit</span>
      <button type="button" aria-label="Zoom in" title="Zoom in"
        disabled={zoom >= 4} onClick={() => setZoom((value) => Math.min(4, value + 0.25))}><ZoomIn size={15} /></button>
      <button type="button" aria-label="Fit preview" title="Fit preview (reset zoom and pan)"
        onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><Maximize2 size={15} /></button>
    </div>}
    {name && <div className="canvas-caption"><span title={name}>{name}</span>{width > 0 && height > 0 && <span>{width} × {height} px</span>}</div>}
    {is3D && previewUrl && <div className="orbit-hint"><Move3D size={14} />Drag to orbit · Shift + arrows</div>}
  </div>;
}
