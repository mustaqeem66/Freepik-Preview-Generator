import { useEffect, useRef, useState } from "react";
import { Image as ImageIcon, Loader2, Move3D } from "lucide-react";

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
}

export function PreviewCanvas({ previewUrl, isLoading, renderError, name, width, height,
  is3D = false, yaw = 45, pitch = 30, onOrbit }: PreviewCanvasProps) {
  const drag = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);
  const [imageError, setImageError] = useState(false);
  useEffect(() => setImageError(false), [previewUrl]);
  const orbit = (y: number, p: number) => onOrbit?.(((y % 360) + 360) % 360, Math.max(-85, Math.min(85, p)));
  const error = renderError || (imageError ? "The rendered image could not be loaded. Select the asset again to retry." : null);
  return <div className={`preview-canvas${is3D ? " orbit-canvas" : ""}`} aria-busy={isLoading}
    role="group" aria-label={is3D ? "3D preview. Drag to orbit; Shift and arrow keys adjust the camera." : "Live preview"}
    tabIndex={is3D ? 0 : undefined}
    onKeyDown={(e) => {
      if (!is3D || !e.shiftKey || !e.key.startsWith("Arrow")) return;
      e.preventDefault(); e.stopPropagation();
      orbit(yaw + (e.key === "ArrowRight" ? 5 : e.key === "ArrowLeft" ? -5 : 0),
        pitch + (e.key === "ArrowUp" ? 5 : e.key === "ArrowDown" ? -5 : 0));
    }}
    onPointerDown={(e) => {
      if (!is3D || !previewUrl || e.button !== 0) return;
      drag.current = { x: e.clientX, y: e.clientY, yaw, pitch };
      e.currentTarget.setPointerCapture(e.pointerId);
    }}
    onPointerMove={(e) => {
      const start = drag.current;
      if (start) orbit(start.yaw + (e.clientX - start.x) * 0.5, start.pitch - (e.clientY - start.y) * 0.5);
    }}
    onPointerUp={() => { drag.current = null; }}
    onPointerCancel={() => { drag.current = null; }}
    onLostPointerCapture={() => { drag.current = null; }}>
    {isLoading && <div className="rendering-indicator" role="status"><Loader2 size={15} className="animate-spin" />Rendering preview…</div>}
    {error && <div className="preview-error" role="alert"><strong>Preview unavailable</strong><p>{error}</p></div>}
    {!error && previewUrl && <img src={previewUrl} alt={name || "Preview"} draggable={false} onError={() => setImageError(true)} />}
    {!error && !previewUrl && !isLoading && <div className="empty-canvas">
      <span className="empty-canvas-icon"><ImageIcon size={32} strokeWidth={1.25} /></span>
      <h2>Your artwork, ready to present</h2><p>Choose a source folder to start.<br />Preview, refine, then export your JPGs.</p>
      <span className="empty-formats">Raster · Vector · 3D · Creator files</span>
    </div>}
    {name && <div className="canvas-caption"><span title={name}>{name}</span>{width > 0 && height > 0 && <span>{width} × {height} px</span>}</div>}
    {is3D && previewUrl && <div className="orbit-hint"><Move3D size={14} />Drag to orbit · Shift + arrows</div>}
  </div>;
}
