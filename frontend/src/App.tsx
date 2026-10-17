import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ApiBridge } from "./api/bridge";
import { useBackend } from "./hooks/useBackend";
import { useSettings } from "./hooks/useSettings";
import { useScanner } from "./hooks/useScanner";
import { usePreview } from "./hooks/usePreview";
import { useBatch } from "./hooks/useBatch";
import { FolderPicker } from "./components/FolderPicker";
import { PreviewCanvas } from "./components/PreviewCanvas";
import { SettingsPanel } from "./components/SettingsPanel";
import { BatchProgress } from "./components/BatchProgress";
import { ErrorNotice, NoticeMessage } from "./components/ErrorNotice";

const springTransition = {
  type: "spring" as const,
  stiffness: 460,
  damping: 32,
  mass: 0.8,
};

export default function App() {
  const { isConnected } = useBackend();
  const handleSaveError = (_err: string) => {
    setNotices((prev) => [
      ...prev.filter((n) => n.id !== "save-err"),
      {
        id: "save-err",
        type: "warning",
        message: "Settings could not be saved",
        details: "Your current session can continue, but changes may not persist.",
      },
    ]);
  };
  const { state, setState } = useSettings(handleSaveError);
  const { fileList, isScanning, scannedCount, scanError, scanFolder, cancelScan } = useScanner();
  const [currentIdx, setCurrentIdx] = useState<number>(0);
  const [notices, setNotices] = useState<NoticeMessage[]>([]);

  const activeFile = fileList.length > 0 && currentIdx < fileList.length ? fileList[currentIdx] : undefined;
  const is3D = activeFile?.is_3d || false;

  const { previewDataUrl, previewMeta, isLoading, renderError } = usePreview(activeFile, state);
  const { isProcessing, progress, stats, batchErrors, startBatch, cancelBatch } = useBatch();

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", state.theme);
  }, [state.theme]);

  // Sync scan on input folder restoration
  useEffect(() => {
    if (state.inputFolder) {
      scanFolder(state.inputFolder);
    }
  }, [state.inputFolder, scanFolder]);

  // Notice sync for scan or render errors
  useEffect(() => {
    if (scanError) {
      setNotices((prev) => [
        ...prev.filter((n) => n.id !== "scan-err"),
        { id: "scan-err", type: "error", message: "Folder Scan Error", details: scanError },
      ]);
    }
  }, [scanError]);

  const handleDismissNotice = (id: string) => {
    setNotices((prev) => prev.filter((n) => n.id !== id));
  };

  const handleBrowseInput = async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const folder = await api.browse_input_folder();
        if (folder) {
          setState((prev) => ({
            ...prev,
            inputFolder: folder,
            outputFolder: prev.sameFolder || !prev.outputFolder ? folder : prev.outputFolder,
          }));
          scanFolder(folder);
        }
      }
    } catch (e) {
      console.error("Browse input folder failed:", e);
    }
  };

  const handleBrowseOutput = async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const folder = await api.browse_output_folder();
        if (folder) {
          setState((prev) => ({ ...prev, outputFolder: folder }));
        }
      }
    } catch (e) {
      console.error("Browse output folder failed:", e);
    }
  };

  const handleBrowseLogo = async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const logo = await api.browse_logo();
        if (logo) setState((prev) => ({ ...prev, logoPath: logo }));
      }
    } catch (e) {
      console.error("Browse logo failed:", e);
    }
  };

  const handleBrowseFont = async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const font = await api.browse_font();
        if (font) setState((prev) => ({ ...prev, fontPath: font }));
      }
    } catch (e) {
      console.error("Browse font failed:", e);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", padding: "18px 24px", gap: "14px" }}>
      {/* Top Header */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: 800, display: "flex", alignItems: "center", gap: "8px" }}>
            <span>PreviewGen</span>
            <span style={{ fontSize: "11px", fontWeight: 700, padding: "2px 8px", background: "var(--chip-bg)", color: "var(--accent)", borderRadius: "6px" }}>
              STUDIO
            </span>
          </h1>
          <p style={{ fontSize: "12px", color: "var(--text-sec)", marginTop: "2px" }}>
            Create marketplace-ready JPG previews with diagonal backgrounds, custom branding & text
          </p>
          {!isConnected && (
            <div style={{ marginTop: "4px", padding: "3px 8px", background: "rgba(239,68,68,0.15)", color: "#EF4444", borderRadius: "4px", fontSize: "11px", fontWeight: 600, display: "inline-block" }}>
              ⚠️ Disconnected from Python backend. Features may be unavailable.
            </div>
          )}
        </div>

        {/* Theme Toggle */}
        <motion.div
          whileTap={{ scale: 0.95 }}
          onClick={() => setState((s) => ({ ...s, theme: s.theme === "light" ? "dark" : "light" }))}
          style={{
            width: "60px",
            height: "30px",
            background: "var(--chip-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: "15px",
            display: "flex",
            alignItems: "center",
            padding: "3px",
            cursor: "pointer",
          }}
        >
          <motion.div
            layout
            transition={springTransition}
            style={{
              width: "24px",
              height: "24px",
              borderRadius: "50%",
              background: state.theme === "dark" ? "#1E1E1E" : "#EBF3F8",
              marginLeft: state.theme === "dark" ? "30px" : "0px",
            }}
          />
        </motion.div>
      </header>

      {/* Visible notices banner */}
      <ErrorNotice notices={notices} onDismiss={handleDismissNotice} />

      {/* Main Studio Viewport */}
      <div style={{ display: "flex", flex: 1, gap: "18px", overflow: "hidden" }}>
        {/* Left Column: Configuration Controls */}
        <div style={{ width: "450px", display: "flex", flexDirection: "column", gap: "12px", overflowY: "auto", paddingRight: "6px" }}>
          {/* Card 1: Folder Picker */}
          <div style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: "12px", padding: "16px" }}>
            <FolderPicker
              inputFolder={state.inputFolder}
              outputFolder={state.outputFolder}
              sameFolder={state.sameFolder}
              onBrowseInput={handleBrowseInput}
              onBrowseOutput={handleBrowseOutput}
              onToggleSameFolder={(checked) => setState((s) => ({ ...s, sameFolder: checked }))}
            />
            {isScanning && (
              <div style={{ marginTop: "10px", padding: "6px 10px", background: "var(--chip-bg)", borderRadius: "6px", display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--accent)" }}>
                <span>Scanning assets… {scannedCount > 0 ? `(${scannedCount} items)` : ""}</span>
                <button type="button" onClick={cancelScan} style={{ background: "none", border: "none", color: "#EF4444", fontWeight: 700, cursor: "pointer" }}>
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Cards 2-5: Branding & Rendering Settings */}
          <SettingsPanel
            state={state}
            onChange={(patch) => setState((s) => ({ ...s, ...patch }))}
            onBrowseLogo={handleBrowseLogo}
            onBrowseFont={handleBrowseFont}
            is3D={is3D}
          />

          {/* Batch Progress & Generation */}
          <BatchProgress
            isProcessing={isProcessing}
            progress={progress}
            stats={stats}
            batchErrors={batchErrors}
            onStartBatch={() => startBatch(state.inputFolder, state.outputFolder, fileList.length, state)}
            onCancelBatch={cancelBatch}
            canStart={!isProcessing && fileList.length > 0}
          />
        </div>

        {/* Right Column: Live Interactive Canvas & File Navigator */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "10px", overflow: "hidden" }}>
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
            <PreviewCanvas
              previewDataUrl={previewDataUrl}
              isLoading={isLoading}
              renderError={renderError}
              name={activeFile?.name || ""}
              width={previewMeta.width}
              height={previewMeta.height}
            />
          </div>

          {/* Bottom File Navigator */}
          {fileList.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <button
                  type="button"
                  disabled={currentIdx === 0}
                  onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
                  style={{ padding: "4px 8px", borderRadius: "6px", border: "1px solid var(--card-border)", background: "var(--surface)", cursor: currentIdx === 0 ? "not-allowed" : "pointer" }}
                >
                  <ChevronLeft size={16} />
                </button>
                <span style={{ fontSize: "12px", fontWeight: 600 }}>
                  {currentIdx + 1} / {fileList.length}
                </span>
                <button
                  type="button"
                  disabled={currentIdx >= fileList.length - 1}
                  onClick={() => setCurrentIdx((i) => Math.min(fileList.length - 1, i + 1))}
                  style={{ padding: "4px 8px", borderRadius: "6px", border: "1px solid var(--card-border)", background: "var(--surface)", cursor: currentIdx >= fileList.length - 1 ? "not-allowed" : "pointer" }}
                >
                  <ChevronRight size={16} />
                </button>
                <span style={{ fontSize: "12px", color: "var(--text-sec)", marginLeft: "8px" }}>
                  {activeFile?.name}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
