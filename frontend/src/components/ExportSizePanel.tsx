import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, Loader2, Lock, Maximize2, X } from "lucide-react";
import { ApiBridge } from "../api/bridge";
import { AssetProbe } from "../types";

const PRESETS = [1024, 2048, 2400, 4096, 8192];
// Coalesces per-keystroke backend dimension requests; low enough to feel instant.
const DIMENSION_REQUEST_DEBOUNCE_MS = 180;
const KIND_LABELS: Record<string, string> = {
  vector: "Vector — resizable", procedural: "Rendered — resizable", raster: "Raster — limited",
};
export interface ExportSizePanelProps {
  filePath?: string;
  probe: AssetProbe | null;
  isProbing: boolean;
  aspectWidth: number;
  aspectHeight: number;
  outputWidth: number;
  outputHeight: number;
  onChange: (width: number, height: number) => void;
  onExport: () => void;
  canExport: boolean;
  isExporting: boolean;
  disabled: boolean;
}

export function ExportSizePanel({ filePath, probe, isProbing, aspectWidth, aspectHeight, outputWidth, outputHeight,
  onChange, onExport, canExport, isExporting, disabled }: ExportSizePanelProps) {
  const [open, setOpen] = useState(false);
  const nativeW = probe?.nativeWidth;
  const nativeH = probe?.nativeHeight;
  const nativeLongest = nativeW && nativeH ? Math.max(nativeW, nativeH) : null;
  const maxLongest = Math.min(probe?.maxDimension ?? 8192,
    probe?.resizable === false ? nativeLongest ?? 8192 : 8192);
  const ratio = (aspectWidth > 0 && aspectHeight > 0 ? aspectWidth / aspectHeight : (nativeW || 1) / (nativeH || 1));
  const longest = outputWidth > 0 && outputHeight > 0 ? Math.min(Math.max(outputWidth, outputHeight), maxLongest)
    : nativeLongest ?? probe?.defaultDimension ?? 2400;
  const displayW = ratio >= 1 ? longest : Math.max(1, Math.round(longest * ratio));
  const displayH = ratio >= 1 ? Math.max(1, Math.round(longest / ratio)) : longest;
  const [draftW, setDraftW] = useState(String(displayW));
  const [draftH, setDraftH] = useState(String(displayH));
  useEffect(() => { setDraftW(String(displayW)); setDraftH(String(displayH)); }, [displayW, displayH]);
  const requestSeqRef = useRef(0);
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (pendingTimerRef.current !== null) clearTimeout(pendingTimerRef.current);
  }, []);
  useEffect(() => {
    // Picking another asset invalidates the dimension request in flight for
    // the previous one, otherwise its reply would size the new export.
    requestSeqRef.current += 1;
    if (pendingTimerRef.current !== null) {
      clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
  }, [filePath]);
  const cancelPendingDimensionRequest = () => {
    requestSeqRef.current += 1;
    if (pendingTimerRef.current !== null) {
      clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
  };
  const applyLongest = (requested: number) => {
    const target = Math.max(1, Math.min(maxLongest, Math.round(requested)));
    const targetW = ratio >= 1 ? target : Math.max(1, Math.round(target * ratio));
    const targetH = ratio >= 1 ? Math.max(1, Math.round(target / ratio)) : target;
    const seq = ++requestSeqRef.current;

    // Commit the local computation immediately: an export started before the
    // backend reconciles must never write at previously selected dimensions.
    onChange(targetW, targetH);
    if (!filePath) return;

    // Authoritative backend resolution: reconcile with canonical calculations.
    if (pendingTimerRef.current !== null) clearTimeout(pendingTimerRef.current);
    pendingTimerRef.current = setTimeout(async () => {
      try {
        const api = await ApiBridge.getApi(500);
        if (api?.calculate_export_dimensions) {
          const res = await api.calculate_export_dimensions(filePath, targetW, targetH);
          // A newer keystroke/preset supersedes this response; discarding it
          // prevents an out-of-order backend reply from committing stale dims.
          if (seq !== requestSeqRef.current) return;
          if (res?.ok && res.value) onChange(res.value.width, res.value.height);
        }
      } catch {
        // Keep the locally computed dimensions.
      }
    }, DIMENSION_REQUEST_DEBOUNCE_MS);
  };
  const applyOriginal = () => {
    // "Original" resets to native size; a pending reconcile must not override it.
    cancelPendingDimensionRequest();
    onChange(0, 0);
  };
  return <div className="export-control">
    {open && <section className="export-popover" data-testid="export-size-panel" aria-label="JPG export settings"
      onKeyDown={(e) => { if (e.key === "Escape") { setOpen(false); e.stopPropagation(); } }}>
      <div className="section-heading"><h2>Export size</h2><button type="button" className="icon-button"
        aria-label="Close export size panel" onClick={() => setOpen(false)}><X size={15} /></button></div>
      <span className="format-badge" data-testid="asset-kind-badge">{isProbing ? "Probing…" : KIND_LABELS[probe?.kind ?? ""] || "Size not yet available"}</span>
      <p className="muted">Applies to single and batch exports. Each asset keeps its own aspect ratio.</p>
      <div className="paired-fields">
        <label className="field-label">Width (px)<input type="number" min={1} max={maxLongest}
          data-testid="output-width" aria-label="Export width in pixels" value={draftW} disabled={disabled}
          onBlur={() => setDraftW(String(displayW))} onChange={(e) => {
            setDraftW(e.target.value); const value = Number(e.target.value);
            if (Number.isFinite(value) && value >= 1) applyLongest(ratio >= 1 ? value : value / ratio);
          }} /></label>
        <label className="field-label">Height (px)<input type="number" min={1} max={maxLongest}
          data-testid="output-height" aria-label="Export height in pixels" value={draftH} disabled={disabled}
          onBlur={() => setDraftH(String(displayH))} onChange={(e) => {
            setDraftH(e.target.value); const value = Number(e.target.value);
            if (Number.isFinite(value) && value >= 1) applyLongest(ratio >= 1 ? value * ratio : value);
          }} /></label>
      </div>
      <span className="muted aspect-note"><Lock size={12} />Aspect ratio preserved</span>
      <div className="size-presets"><button type="button" className="button" data-testid="preset-0"
        disabled={disabled} onClick={applyOriginal}>Original</button>
        {PRESETS.map((value) => <button key={value} type="button" className="button" data-testid={`preset-${value}`}
          disabled={disabled || value > maxLongest} onClick={() => applyLongest(value)}>{value}</button>)}</div>
      {probe?.resizable === false && <p className="export-warning" data-testid="raster-warning"><AlertTriangle size={14} />
        Raster previews are never enlarged{nativeW && nativeH ? ` beyond ${nativeW} × ${nativeH} px` : " beyond their native pixels"}.</p>}
      <button type="button" className="button primary" data-testid="export-preview" disabled={disabled || !canExport || isExporting}
        onClick={onExport}>{isExporting ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
        {isExporting ? "Exporting…" : "Export JPG"}</button>
    </section>}
    <button type="button" className="button export-toggle" data-testid="export-size-toggle" aria-label="Export size options"
      aria-expanded={open} disabled={disabled} onClick={() => setOpen(!open)}><Maximize2 size={15} />
      {disabled ? "Export size" : `${displayW} × ${displayH}`}<span className="format-badge">JPG</span></button>
  </div>;
}
