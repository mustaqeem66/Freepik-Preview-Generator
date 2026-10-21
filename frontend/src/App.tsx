import { useCallback, useEffect, useState } from "react";
import { PaneResizer } from "./components/PaneResizer";
import { Box, ChevronLeft, ChevronRight, FolderOpen, Layers, Moon, RefreshCw, Sun, Activity } from "lucide-react";
import { ApiBridge } from "./api/bridge";
import { useBackend } from "./hooks/useBackend";
import { useSettings } from "./hooks/useSettings";
import { useScanner } from "./hooks/useScanner";
import { usePreview } from "./hooks/usePreview";
import { useAssetProbe } from "./hooks/useAssetProbe";
import { useBatch } from "./hooks/useBatch";
import { FolderPicker } from "./components/FolderPicker";
import { PreviewCanvas } from "./components/PreviewCanvas";
import { ExportSizePanel } from "./components/ExportSizePanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { BatchProgress } from "./components/BatchProgress";
import { FileList } from "./components/FileList";
import { ErrorNotice, NoticeMessage } from "./components/ErrorNotice";
import type { LifecycleState, PyWebViewApi } from "./types";

const LIFECYCLE_LABELS: Record<LifecycleState, string> = {
  idle: "Ready", scanning: "Scanning", "scan-cancelling": "Cancelling scan", "scan-cancelled": "Scan cancelled",
  "scan-truncated": "Partial scan", previewing: "Rendering", generating: "Generating",
  "batch-cancelling": "Cancelling batch", cancelled: "Batch cancelled", completed: "Completed",
  "completed-with-warnings": "Completed with warnings", "completed-with-errors": "Completed with errors", failed: "Failed",
};

const readPaneWidth = (key: string, fallback: number, min: number, max: number) => {
  try {
    const value = Number(window.localStorage.getItem(key));
    return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
  } catch {
    return fallback;
  }
};

export default function App() {
  const [libraryWidth, setLibraryWidth] = useState(() => readPaneWidth("previewgen.libraryWidth", 250, 200, 360));
  const [inspectorWidth, setInspectorWidth] = useState(() => readPaneWidth("previewgen.inspectorWidth", 300, 260, 380));
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const updateSize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);
  useEffect(() => {
    try {
      window.localStorage.setItem("previewgen.libraryWidth", String(libraryWidth));
      window.localStorage.setItem("previewgen.inspectorWidth", String(inspectorWidth));
    } catch {
      // Storage might be unavailable in a restricted embedded WebView.
    }
  }, [libraryWidth, inspectorWidth]);
  const isWideWorkspace = viewportWidth > 850;
  const widthBudget = viewportWidth - (viewportWidth > 1100 ? 36 : 20) - 16;
  const actualLibraryWidth = Math.min(libraryWidth, Math.max(200, widthBudget - inspectorWidth - 292));
  const actualInspectorWidth = Math.min(inspectorWidth, Math.max(260, widthBudget - actualLibraryWidth - 292));
  const { status, capabilities, retry } = useBackend();
  const [notices, setNotices] = useState<NoticeMessage[]>([]);
  const showNotice = useCallback((notice: NoticeMessage) => {
    setNotices((previous) => [...previous.filter((item) => item.id !== notice.id), notice]);
  }, []);
  const handleSaveError = useCallback((details: string) => {
    showNotice({ id: "save-error", type: "warning", message: "Settings could not be saved", details });
  }, [showNotice]);
  const { state, setState, isLoaded, saveStatus, retrySave } = useSettings(handleSaveError, capabilities.canSaveSettings);
  const { fileList, isScanning, scanStatus, scanTruncationReasons, scanDiscovered,
    scannedCount, scanError, scanFolder, cancelScan } = useScanner();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  // The selection is the single source of truth for the list highlight, the
  // preview and the export target. Deriving it with a fallback to index 0 let a
  // re-scan silently retarget whichever asset happened to sort first.
  useEffect(() => {
    if (fileList.length === 0) {
      if (selectedPath !== null) setSelectedPath(null);
      return;
    }
    if (!selectedPath || !fileList.some((file) => file.path === selectedPath)) {
      setSelectedPath(fileList[0].path);
    }
  }, [fileList, selectedPath]);
  const currentIdx = fileList.findIndex((file) => file.path === selectedPath);
  const activeFile = currentIdx >= 0 ? fileList[currentIdx] : undefined;
  const scanReady = !isScanning && (scanStatus === "completed" || scanStatus === "scan-truncated");
  const previewFile = capabilities.canPreview && scanReady ? activeFile : undefined;
  const { previewUrl, previewMeta, isLoading, renderError } = usePreview(previewFile, state);
  const probeFile = capabilities.canProbe && scanReady ? activeFile : undefined;
  const { probe, isProbing } = useAssetProbe(probeFile);
  const [isExporting, setIsExporting] = useState(false);
  const { isProcessing, batchStatus, progress, stats, batchErrors, truncationReasons, discovered,
    requiresTruncationAck, acknowledgeTruncation, startBatch, cancelBatch } = useBatch();
  const busy = isProcessing || isExporting;
  const is3D = activeFile?.is_3d === true;
  const lifecycle: LifecycleState = isProcessing ? (batchStatus === "batch-cancelling" ? batchStatus : "generating")
    : isScanning ? (scanStatus === "scan-cancelling" ? scanStatus : "scanning")
    : isLoading ? "previewing" : scanStatus === "scan-cancelled" || scanStatus === "scan-truncated" ? scanStatus
    : batchStatus !== "idle" ? batchStatus : "idle";

  useEffect(() => { document.documentElement.setAttribute("data-theme", state.theme); }, [state.theme]);
  useEffect(() => {
    if (isLoaded && capabilities.canScan) void scanFolder(state.inputFolder);
  }, [isLoaded, capabilities.canScan, state.inputFolder, scanFolder]);
  useEffect(() => {
    if (scanError) showNotice({ id: "scan-error", type: "error", message: "Folder scan failed", details: scanError });
    else setNotices((previous) => previous.filter((item) => item.id !== "scan-error"));
  }, [scanError, showNotice]);

  // A native folder dialog intentionally hides files. Explain genuinely empty scans,
  // but never show this warning for an incomplete, cancelled or failed scan.
  useEffect(() => {
    if (scanStatus === "completed" && !isScanning && !scanError && state.inputFolder && fileList.length === 0) {
      showNotice({
        id: "no-assets",
        type: "info",
        message: "No supported assets found",
        details: "This folder contains no supported files within the scan limits. Try another folder or check its contents.",
      });
    } else {
      setNotices((previous) => previous.filter((notice) => notice.id !== "no-assets"));
    }
  }, [scanStatus, isScanning, scanError, state.inputFolder, fileList.length, showNotice]);

  const selectIndex = useCallback((index: number) => {
    if (!busy && fileList[index]) setSelectedPath(fileList[index].path);
  }, [busy, fileList]);
  useEffect(() => {
    const navigate = (event: KeyboardEvent) => {
      if (busy || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea, select, [contenteditable=true], [role=listbox], dialog")) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        selectIndex(Math.max(0, Math.min(fileList.length - 1, currentIdx + (event.key === "ArrowRight" ? 1 : -1))));
      }
    };
    window.addEventListener("keydown", navigate);
    return () => window.removeEventListener("keydown", navigate);
  }, [busy, currentIdx, fileList.length, selectIndex]);

  const browse = async (method: "browse_input_folder" | "browse_output_folder" | "browse_logo" | "browse_font") => {
    if (!capabilities.canBrowse || busy) return;
    try {
      const api = await ApiBridge.getApi();
      if (!api) throw new Error("Backend unavailable. Reconnect to choose files.");
      const path = await api[method]();
      if (!path) return;
      const field = method === "browse_input_folder" ? "inputFolder" : method === "browse_output_folder" ? "outputFolder"
        : method === "browse_logo" ? "logoPath" : "fontPath";
      setState((previous) => ({ ...previous, [field]: path }));
    } catch (error) {
      showNotice({ id: "browse-error", type: "error", message: "Could not open the file picker",
        details: error instanceof Error ? error.message : "Please paste the folder path instead." });
    }
  };

  const openDiagnostics = async () => {
    try {
      const api = await ApiBridge.getApi();
      if (!api?.open_diagnostics_folder) throw new Error("Diagnostics require the current desktop version.");
      const result = await api.open_diagnostics_folder();
      if (!result.ok) throw new Error(result.error || "Unable to open diagnostics folder");
    } catch (error) {
      showNotice({ id: "diagnostics-error", type: "warning", message: "Could not open diagnostics",
        details: error instanceof Error ? error.message : "Check the logs directory manually." });
    }
  };

  const handleExport = async () => {
    if (!activeFile || busy || !scanReady || !capabilities.canGenerate) return;
    setIsExporting(true);
    try {
      const api = await ApiBridge.getApi();
      if (!api?.export_preview) throw new Error("Single-file export is unavailable. Reconnect to the desktop backend.");
      const response = await api.export_preview(activeFile.path, state);
      if (!response.ok || !response.value) {
        throw new Error(
          response.code === "UNAUTHORIZED_PATH"
            ? "PreviewGen can only write inside a folder you chose. Pick an output folder and try again."
            : response.error || "Export failed"
        );
      }
      const value = response.value;
      showNotice({ id: "export-status", type: "info", message: value.skipped ? "Existing JPG kept — export skipped"
        : `Exported ${value.width} × ${value.height} px`, details: value.path });
    } catch (error) {
      showNotice({ id: "export-status", type: "error", message: "Export failed",
        details: error instanceof Error ? error.message : "Unknown export error" });
    } finally { setIsExporting(false); }
  };

  const openOutput = async () => {
    try {
      const api: PyWebViewApi | undefined = await ApiBridge.getApi();
      if (!api) throw new Error("Backend unavailable");
      const result = await api.open_folder(state.sameFolder ? state.inputFolder : state.outputFolder || state.inputFolder);
      if (!result.ok) throw new Error(result.message || result.error || "Could not open the output folder");
    } catch (error) {
      showNotice({ id: "open-output", type: "error", message: "Could not open the output folder",
        details: error instanceof Error ? error.message : undefined });
    }
  };

  return <div className="studio-shell">
    <header className="studio-toolbar">
      <div className="brand"><span className="brand-mark"><Layers size={21} strokeWidth={1.6} /></span>
        <div><h1>PreviewGen<span className="studio-badge">Studio</span></h1><p>Make every asset presentation-ready.</p></div></div>
      <div className="toolbar-actions">
        <span className="lifecycle-badge" data-testid="lifecycle-state" data-state={lifecycle} role="status"
          title="Last frontend/backend state; a frozen Windows window may not update this label">
          <span className="status-dot" />{LIFECYCLE_LABELS[lifecycle]}</span>
        <span className="settings-save-status" role="status" aria-live="polite" title="Settings are saved locally">
          {saveStatus === "saved" ? "Settings saved" : saveStatus === "saving" ? "Saving…" :
            saveStatus === "error" ? "Settings unsaved" : saveStatus === "unsaved" ? "Unsaved changes" : ""}
        </span>
        {saveStatus === "error" && <button type="button" className="button" onClick={retrySave}>Retry save</button>}
        <button type="button" className="button diagnostics-button" title="Open local diagnostic logs (no upload)"
          disabled={!capabilities.canBrowse}
          onClick={() => void openDiagnostics()}><Activity size={15} /> Diagnostics</button>
        <button type="button" className="icon-button theme-toggle" aria-label={state.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setState((previous) => ({ ...previous, theme: previous.theme === "light" ? "dark" : "light" }))}>
          {state.theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
      </div>
    </header>
    {status !== "ready" && <div className="connection-banner" role="status">
      <span>{status === "connecting" ? "Connecting to the desktop backend…" : status === "degraded"
        ? "The backend is connected but not ready to render." : "Desktop backend disconnected. File and export actions are unavailable."}</span>
      {status !== "connecting" && <button type="button" className="button" onClick={retry}>Reconnect</button>}
    </div>}
    <ErrorNotice notices={notices} onDismiss={(id) => setNotices((previous) => previous.filter((item) => item.id !== id))} />

    <main className="studio-workspace" style={isWideWorkspace ? {
      gridTemplateColumns: `${actualLibraryWidth}px 6px minmax(280px, 1fr) 6px ${actualInspectorWidth}px`
    } : undefined}>
      <aside className="library-pane" aria-label="Asset library">
        <FolderPicker inputFolder={state.inputFolder} outputFolder={state.outputFolder} sameFolder={state.sameFolder}
          disabled={busy || !isLoaded || !capabilities.canBrowse}
          onBrowseInput={() => void browse("browse_input_folder")} onBrowseOutput={() => void browse("browse_output_folder")}
          onCommitInput={(inputFolder) => setState((previous) => ({ ...previous, inputFolder }))}
          onToggleSameFolder={(sameFolder) => setState((previous) => ({ ...previous, sameFolder }))} />
        <div className="library-heading"><h2>Assets<span className="count-badge">{fileList.length}</span></h2>
          <button type="button" className="icon-button" aria-label="Rescan source folder" disabled={!state.inputFolder || busy || isScanning || !capabilities.canScan}
            onClick={() => void scanFolder(state.inputFolder)}><RefreshCw size={14} /></button></div>
        {isScanning && <div className="scan-notice" role="status"><span>Scanning… {scannedCount || ""}</span>
          <button type="button" className="text-button" onClick={() => void cancelScan()} disabled={scanStatus === "scan-cancelling"}>Cancel</button></div>}
        {scanStatus === "scan-cancelled" && <p className="scan-notice" data-testid="scan-cancelled">Scan cancelled. Previous results are shown; rescan to export.</p>}
        {scanStatus === "scan-truncated" && <p className="scan-notice" data-testid="scan-truncated">
          Partial list: {fileList.length} of {scanDiscovered} discovered. {scanTruncationReasons.join(", ")}. Batch export scans the source again.</p>}
        {fileList.length > 0 ? <FileList files={fileList} activeIndex={currentIdx} onSelect={selectIndex} height={260} />
          : <div className="empty-library"><FolderOpen size={24} strokeWidth={1.3} /><p>{isScanning ? "Finding your artwork…" : state.inputFolder
            ? "No assets listed. Check the folder path or rescan." : "Choose a folder to build your asset library."}</p></div>}
        <div className="library-footnote"><span className="status-dot" />Local processing · No uploads</div>
      </aside>
      {isWideWorkspace && <PaneResizer label="Resize asset library" value={actualLibraryWidth}
        initial={250} min={200} max={360} onChange={setLibraryWidth} />}
      <section className="canvas-pane" aria-label="Preview workspace">
        <div className="canvas-toolbar"><div className="asset-title">{is3D ? <Box size={16} /> : <Layers size={16} />}
          <span title={activeFile?.name}>{activeFile?.name || "Live preview"}</span>{activeFile && <span className="format-badge">{activeFile.ext}</span>}</div>
          <div className="asset-navigation"><button type="button" className="icon-button" aria-label="Previous asset"
            disabled={busy || currentIdx <= 0 || !activeFile} onClick={() => selectIndex(currentIdx - 1)}><ChevronLeft size={16} /></button>
            <span className="tabular-nums">{fileList.length ? `${Math.max(1, currentIdx + 1)} / ${fileList.length}` : "0 assets"}</span>
            <button type="button" className="icon-button" aria-label="Next asset" disabled={busy || currentIdx >= fileList.length - 1}
              onClick={() => selectIndex(currentIdx + 1)}><ChevronRight size={16} /></button></div></div>
        <div className="canvas-stage"><PreviewCanvas previewUrl={previewUrl} isLoading={isLoading} renderError={renderError}
          name={previewFile?.name || ""} width={previewMeta.width} height={previewMeta.height} is3D={is3D && !busy}
          hasSourceFolder={Boolean(state.inputFolder)} canChooseFolder={!busy && capabilities.canBrowse && isLoaded}
          onChooseFolder={() => void browse("browse_input_folder")}
          yaw={state.yaw} pitch={state.pitch} onOrbit={(yaw, pitch) => setState((previous) => ({ ...previous, yaw, pitch }))} />
          <ExportSizePanel filePath={activeFile?.path} probe={probe} isProbing={isProbing} aspectWidth={previewMeta.width} aspectHeight={previewMeta.height}
            outputWidth={state.outputWidth} outputHeight={state.outputHeight}
            onChange={(outputWidth, outputHeight) => setState((previous) => ({ ...previous, outputWidth, outputHeight }))}
            onExport={() => void handleExport()} canExport={capabilities.canGenerate && !busy && scanReady}
            isExporting={isExporting} disabled={!activeFile || !scanReady} /></div>
        <div className="canvas-footnote"><span>Diagonal split · Original proportions</span><span>JPG is opaque; checkerboard is printed.</span></div>
      </section>
      {isWideWorkspace && <PaneResizer label="Resize inspector" value={actualInspectorWidth}
        initial={300} min={260} max={380} reverse onChange={setInspectorWidth} />}
      <aside className="inspector-pane" aria-label="Preview inspector">
        <div className="inspector-heading"><h2>Inspector</h2><span className="muted">Live adjustments</span></div>
        <fieldset disabled={busy || !isLoaded}><legend className="sr-only">Preview settings</legend>
          <SettingsPanel state={state} onChange={(patch) => setState((previous) => ({ ...previous, ...patch }))}
            onBrowseLogo={() => void browse("browse_logo")} onBrowseFont={() => void browse("browse_font")} is3D={is3D} />
        </fieldset>
      </aside>
    </main>
    <footer className="studio-footer"><BatchProgress isProcessing={isProcessing} progress={progress} stats={stats} batchErrors={batchErrors}
      truncated={requiresTruncationAck} truncationReasons={truncationReasons} discovered={discovered}
      onStartBatch={() => { if (!busy && scanReady) void startBatch(state.inputFolder, state.outputFolder, fileList.length, state); }}
      onCancelBatch={() => void cancelBatch()} canStart={capabilities.canGenerate && !busy && scanReady && fileList.length > 0 && !requiresTruncationAck} />
      <button type="button" className="button" disabled={!state.inputFolder || !capabilities.canOpenReport || busy} onClick={() => void openOutput()}><FolderOpen size={15} />Open Output Folder</button>
    </footer>
    {requiresTruncationAck && <dialog className="warning-dialog" ref={(dialog) => { if (dialog && !dialog.open) dialog.showModal(); }}
      aria-labelledby="truncation-title" onCancel={(event) => event.preventDefault()} data-testid="truncation-ack">
      <h2 id="truncation-title">Batch completed with warnings</h2><p>Discovery stopped early ({truncationReasons.join(", ") || "a safety limit"}).
        Only part of the source was processed. Review the batch report before continuing.</p>
      <button type="button" className="button primary" autoFocus onClick={acknowledgeTruncation}>I understand — continue</button>
    </dialog>}
  </div>;
}
