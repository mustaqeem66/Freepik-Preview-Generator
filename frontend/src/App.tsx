import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FolderOpen,
  Sun,
  Moon,
  Upload,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  RefreshCw,
  Type,
  Image as ImageIcon,
  Box,
  Layers,
  Sparkles,
} from "lucide-react";
import { FileInfo, PreviewState, BatchSummary, PyWebViewApi } from "./types";
import { ApiBridge } from "./api/bridge";

// Apple-calibrated spring physics
const springTransition = {
  type: "spring" as const,
  stiffness: 460,
  damping: 32,
  mass: 0.8,
};

const defaultState: PreviewState = {
  inputFolder: "",
  outputFolder: "",
  sameFolder: false,
  invertTriangles: true,
  solidColor: "#FFFFFF",
  logoPath: "",
  logoScale: 100,
  logoOpacity: 90,
  logoPosX: 88,
  logoPosY: 5,
  text: "100% TRANSPARENT",
  textPosX: 5,
  textPosY: 5,
  textColor: "#FFFFFF",
  fontPath: "",
  fontScale: 100,
  hasOutline: true,
  outlineColor: "#000000",
  outlineThickness: 2,
  opacity: 90,
  yaw: 45,
  pitch: 30,
  theme: "light",
  overwritePolicy: "rename",
};

export default function App() {
  const [state, setState] = useState<PreviewState>(defaultState);
  const [fileList, setFileList] = useState<FileInfo[]>([]);
  const [currentIdx, setCurrentIdx] = useState<number>(0);
  const [previewDataUrl, setPreviewDataUrl] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<{ width: number; height: number; name: string }>({
    width: 0,
    height: 0,
    name: "",
  });
  const [, setIsLoadingPreview] = useState<boolean>(false);
  const [fitToView, setFitToView] = useState<boolean>(true);
  const [is3DDragging, setIs3DDragging] = useState<boolean>(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [active3DPreset, setActive3DPreset] = useState<string>("Isometric 3/4");

  // Batch progress
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [progress, setProgress] = useState<{ current: number; total: number; message: string }>({
    current: 0,
    total: 0,
    message: "Ready to process",
  });
  const [stats, setStats] = useState<{ success: number; failed: number }>({ success: 0, failed: 0 });
  const [batchErrors, setBatchErrors] = useState<string[]>([]);
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  // 3D drag ref & settings loaded gate
  const dragStartPos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const isLoadedRef = useRef<boolean>(false);

  // Theme application
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", state.theme);
  }, [state.theme]);



  // Initial Load from Python Backend with pywebviewready listener
  useEffect(() => {
    let unmounted = false;
    const init = async () => {
      const api = await ApiBridge.getApi(5000);
      if (api && !unmounted) {
        try {
          // P0-1: Notify backend that React frontend is mounted and interactive
          if (api.frontend_ready) {
            await api.frontend_ready().catch(() => {});
          }
          const res = await api.get_initial_state();
          const saved: Partial<PreviewState> | undefined = res && "value" in res ? res.value : (res as Partial<PreviewState>);
          if (saved && !unmounted) {
            setState((prev) => ({ ...prev, ...saved }));
            if (saved.inputFolder) {
              scanFolder(saved.inputFolder);
            }
          }
        } catch (e) {
          console.error("Failed to load initial state:", e);
        } finally {
          isLoadedRef.current = true;
        }
      } else if (!api && !unmounted) {
        setIsBackendConnected(false);
      }
    };

    // Register batch progress listeners from Python
    window.__onBatchProgress = (current: number, total: number, message: string) => {
      setProgress({ current, total, message });
    };

    window.__onBatchFinishedSummary = (summary: BatchSummary) => {
      setIsProcessing(false);
      const { success, failed, skipped, cancelled, errors, duration } = summary;
      setProgress({
        current: success + failed + (skipped || 0),
        total: summary.planned || (success + failed + (skipped || 0)),
        message: cancelled
          ? `Cancelled after ${duration}s. (${success} saved, ${failed} failed, ${skipped || 0} skipped)`
          : failed > 0
          ? `Completed with issues in ${duration}s: ${success} succeeded, ${failed} failed, ${skipped || 0} skipped.`
          : `Completed in ${duration}s! ${success} previews saved (${skipped || 0} skipped).`,
      });
      setStats({ success, failed });
      if (errors && errors.length > 0) {
        setBatchErrors(errors);
      }
    };

    window.__onBatchFinished = (success: number, failed: number, errors: string[], cancelled: boolean) => {
      setIsProcessing(false);
      setProgress({
        current: success + failed,
        total: success + failed,
        message: cancelled
          ? "Processing cancelled."
          : failed > 0
          ? `Completed with issues: ${success} succeeded, ${failed} failed.`
          : `Completed! ${success} previews saved.`,
      });
      setStats({ success, failed });
      if (errors && errors.length > 0) {
        setBatchErrors(errors);
      }
    };

    init();
    window.addEventListener("pywebviewready", init);
    return () => {
      unmounted = true;
      window.removeEventListener("pywebviewready", init);
    };
  }, []);

  // Save settings whenever state changes (debounced by 800ms to eliminate IPC traffic storms)
  useEffect(() => {
    if (!isLoadedRef.current) return;
    const timer = setTimeout(async () => {
      const api = await ApiBridge.getApi(1000);
      if (api) {
        api.save_settings(state).catch(() => {});
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [state]);

  // Debounced live preview refresh (ONLY re-runs when visual rendering properties change, NOT on theme or folder changes!)
  const activeFile = fileList[currentIdx];
  const isCurrent3D = activeFile?.is_3d || false;

  useEffect(() => {
    if (!activeFile) {
      setPreviewDataUrl(null);
      setPreviewMeta({ width: 0, height: 0, name: "" });
      setRenderError(null);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setIsLoadingPreview(true);
      try {
        const api = await ApiBridge.getApi(3000);
        if (api) {
          const res = await api.render_preview(activeFile.path, state);
          if (cancelled) return;
          if (res && "value" in res && res.value) {
            setPreviewDataUrl(res.value.dataUrl);
            setPreviewMeta({ width: res.value.width || 0, height: res.value.height || 0, name: activeFile.name });
            setRenderError(null);
          } else if (res && "error" in res && res.error) {
            setRenderError(res.error);
          }
        }
      } catch (err: unknown) {
        if (!cancelled) {
          console.error("Preview render failed:", err);
          setRenderError(err instanceof Error ? err.message : "Failed to render preview");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingPreview(false);
        }
      }
    }, 40);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    activeFile,
    state.text,
    state.opacity,
    state.invertTriangles,
    state.solidColor,
    state.textColor,
    state.hasOutline,
    state.outlineColor,
    state.outlineThickness,
    state.fontScale,
    state.textPosX,
    state.textPosY,
    state.logoPath,
    state.logoScale,
    state.logoOpacity,
    state.logoPosX,
    state.logoPosY,
    state.fontPath,
    state.modelColor,
    state.yaw,
    state.pitch,
  ]);

  // Folder scanning
  const scanFolder = async (folderPath: string) => {
    if (!folderPath) return;
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const res = await api.scan_folder(folderPath);
        if (res?.files) {
          setFileList(res.files);
          setCurrentIdx(0);
          if (res.files.length === 0) {
            setPreviewDataUrl(null);
            setPreviewMeta({ width: 0, height: 0, name: "" });
            setRenderError(null);
          }
        }
      }
    } catch (e) {
      console.error("Scan folder failed:", e);
    }
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
      console.error("Browse input failed:", e);
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
      console.error("Browse output failed:", e);
    }
  };

  const handleOpenOutput = async () => {
    const target = state.outputFolder || state.inputFolder;
    const api = await ApiBridge.getApi(3000);
    if (target && api) {
      api.open_folder(target).catch(() => {});
    }
  };

  const handleBrowseLogo = async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        const logo = await api.browse_logo();
        if (logo) {
          setState((prev) => ({ ...prev, logoPath: logo }));
        }
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
        if (font) {
          setState((prev) => ({ ...prev, fontPath: font }));
        }
      }
    } catch (e) {
      console.error("Browse font failed:", e);
    }
  };

  const handleStartBatch = async () => {
    if (!state.inputFolder) return;
    setIsProcessing(true);
    setStats({ success: 0, failed: 0 });
    setProgress({ current: 0, total: fileList.length, message: "Starting batch generation…" });

    const api = await ApiBridge.getApi(3000);
    if (api) {
      api.start_batch(state.inputFolder, state.outputFolder || state.inputFolder, state).catch(() => {
        setIsProcessing(false);
      });
    }
  };

  const handleCancelBatch = async () => {
    const api = await ApiBridge.getApi(3000);
    if (api) {
      api.cancel_batch().catch(() => {});
    }
  };

  // Keyboard navigation (B-13: do not hijack arrow keys when typing inside inputs)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable) {
          return;
        }
      }
      if (fileList.length <= 1) return;
      if (e.key === "ArrowLeft") {
        setCurrentIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight") {
        setCurrentIdx((i) => Math.min(fileList.length - 1, i + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [fileList]);

  // 3D Canvas Dragging (B-13: release drag even when mouseup fires outside viewport)
  useEffect(() => {
    if (!is3DDragging) return;
    const onGlobalMouseUp = () => setIs3DDragging(false);
    window.addEventListener("mouseup", onGlobalMouseUp);
    return () => window.removeEventListener("mouseup", onGlobalMouseUp);
  }, [is3DDragging]);

  const handleMouseDown3D = (e: React.MouseEvent) => {
    if (!isCurrent3D) return;
    setIs3DDragging(true);
    dragStartPos.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove3D = (e: React.MouseEvent) => {
    if (!is3DDragging || !isCurrent3D) return;
    const dx = e.clientX - dragStartPos.current.x;
    const dy = e.clientY - dragStartPos.current.y;
    dragStartPos.current = { x: e.clientX, y: e.clientY };

    setState((prev) => ({
      ...prev,
      yaw: (((prev.yaw + Math.round(dx * 0.7)) % 360) + 360) % 360,
      pitch: Math.max(-85, Math.min(85, prev.pitch - Math.round(dy * 0.7))),
    }));
    setActive3DPreset("Custom");
  };

  const handleMouseUp3D = () => {
    setIs3DDragging(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", padding: "18px 24px", gap: "16px" }}>
      {/* ─── Top Header Bar ─── */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: "21px", fontWeight: 800, letterSpacing: "-0.3px", display: "flex", alignItems: "center", gap: "8px" }}>
            <span>PreviewGen</span>
            <span style={{ fontSize: "11px", fontWeight: 700, padding: "2px 8px", background: "var(--chip-bg)", color: "var(--accent)", border: "1px solid var(--card-border)", borderRadius: "6px" }}>
              STUDIO
            </span>
          </h1>
          <p style={{ fontSize: "12px", color: "var(--text-sec)", marginTop: "2px" }}>
            Create marketplace-ready JPG previews with customizable diagonal backgrounds & text
          </p>
          {!isBackendConnected && (
            <div
              style={{
                marginTop: "6px",
                padding: "4px 8px",
                background: "rgba(239, 68, 68, 0.15)",
                color: "#EF4444",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                display: "inline-block",
              }}
            >
              ⚠️ Disconnected from Python backend bridge. Features may be offline.
            </div>
          )}
        </div>

        {/* Theme Toggle Pill Switch with Spring Animation */}
        <motion.div
          whileTap={{ scale: 0.95 }}
          onClick={() => setState((s) => ({ ...s, theme: s.theme === "light" ? "dark" : "light" }))}
          style={{
            width: "66px",
            height: "32px",
            background: "var(--chip-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: "16px",
            display: "flex",
            alignItems: "center",
            padding: "3px",
            cursor: "pointer",
            position: "relative",
            boxShadow: "var(--btn-shadow)",
          }}
        >
          <motion.div
            layout
            transition={springTransition}
            style={{
              width: "26px",
              height: "26px",
              borderRadius: "50%",
              background: state.theme === "dark" ? "#1E1E1E" : "#EBF3F8",
              boxShadow: "0 2px 5px rgba(0,0,0,0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginLeft: state.theme === "dark" ? "34px" : "0px",
            }}
          >
            {state.theme === "dark" ? <Sun size={14} color="#FBBF24" /> : <Moon size={14} color="#7FA6B8" />}
          </motion.div>
        </motion.div>
      </header>

      {/* ─── Main Two-Column Layout ─── */}
      <div style={{ display: "flex", flex: 1, gap: "18px", overflow: "hidden" }}>
        {/* ── LEFT COLUMN: Scrollable Cards (Width: 460px) ── */}
        <div
          style={{
            width: "460px",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
            overflowY: "auto",
            paddingRight: "8px",
          }}
        >
          {/* CARD 1: Folders */}
          <div style={cardStyle}>
            <div style={cardTitleStyle}>
              <FolderOpen size={15} color="var(--accent)" /> 1 · Folders
            </div>

            <label style={fieldLabelStyle}>Input Folder or ZIP (2D, 3D, CAD, or ZIP Archives)</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="Folder containing 2D images, 3D models, CAD drawings, or ZIPs"
                value={state.inputFolder}
                onChange={(e) => {
                  const val = e.target.value;
                  setState((s) => ({
                    ...s,
                    inputFolder: val,
                    outputFolder: s.sameFolder || !s.outputFolder ? val : s.outputFolder,
                  }));
                }}
                onBlur={() => {
                  if (state.inputFolder) scanFolder(state.inputFolder);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && state.inputFolder) {
                    scanFolder(state.inputFolder);
                  }
                }}
                style={{ flex: 1 }}
              />
              <motion.button whileHover={{ y: -0.5 }} whileTap={{ scale: 0.97 }} onClick={handleBrowseInput} style={secondaryBtnStyle}>
                Browse…
              </motion.button>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer", marginTop: "4px" }}>
              <input
                type="checkbox"
                checked={state.sameFolder}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setState((s) => ({
                    ...s,
                    sameFolder: checked,
                    outputFolder: checked && s.inputFolder ? s.inputFolder : s.outputFolder,
                  }));
                }}
              />
              Save preview JPGs in the same folder as input files
            </label>

            <label style={fieldLabelStyle}>Output JPG Folder</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                placeholder="Destination folder for previews"
                value={state.outputFolder}
                disabled={state.sameFolder}
                onChange={(e) => {
                  const val = e.target.value;
                  setState((s) => ({ ...s, outputFolder: val }));
                }}
                style={{ flex: 1 }}
              />
              <motion.button whileHover={{ y: -0.5 }} whileTap={{ scale: 0.97 }} onClick={handleBrowseOutput} disabled={state.sameFolder} style={secondaryBtnStyle}>
                Browse…
              </motion.button>
              <motion.button whileHover={{ y: -0.5 }} whileTap={{ scale: 0.97 }} onClick={handleOpenOutput} style={secondaryBtnStyle}>
                Open
              </motion.button>
            </div>
          </div>

          {/* CARD 2: Background Triangle & Colors */}
          <div style={cardStyle}>
            <div style={cardTitleStyle}>
              <Layers size={15} color="var(--accent)" /> 2 · Background Triangle & Colors
            </div>

            <label style={fieldLabelStyle}>Diagonal Split Direction</label>
            <select
              value={state.invertTriangles ? "true" : "false"}
              onChange={(e) => setState((s) => ({ ...s, invertTriangles: e.target.value === "true" }))}
              style={{ width: "100%" }}
            >
              <option value="true">Left Solid / Right Transparent (Recommended)</option>
              <option value="false">Left Transparent / Right Solid</option>
            </select>

            <label style={fieldLabelStyle}>Solid Background Color</label>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <input
                type="color"
                value={state.solidColor}
                onChange={(e) => setState((s) => ({ ...s, solidColor: e.target.value }))}
                style={{ width: "42px", height: "30px", border: "none", borderRadius: "6px", cursor: "pointer" }}
              />
              <span className="tabular-nums" style={{ fontSize: "11px", fontWeight: 700, fontFamily: "monospace" }}>
                {state.solidColor.toUpperCase()}
              </span>
              {["#FFFFFF", "#F8FAFC", "#E2E8F0", "#1E293B"].map((c, i) => {
                const label = ["White", "Off-White", "Light Gray", "Dark"][i];
                const isActive = state.solidColor.toUpperCase() === c.toUpperCase();
                return (
                  <motion.button
                    key={c}
                    whileHover={{ y: -0.5 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => setState((s) => ({ ...s, solidColor: c }))}
                    style={{
                      ...chipStyle,
                      position: "relative",
                      background: isActive ? "var(--chip-active)" : "var(--chip-bg)",
                      color: isActive ? "var(--chip-active-text)" : "var(--text-sec)",
                    }}
                  >
                    {label}
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* CARD 3: Branding & Watermark (Logo + Text) */}
          <div style={cardStyle}>
            <div style={cardTitleStyle}>
              <Sparkles size={15} color="var(--accent)" /> 3 · Branding & Watermark (Logo + Text)
            </div>

            {/* Logo Section */}
            <label style={fieldLabelStyle}>Brand Logo / Icon (Optional)</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleBrowseLogo}
                style={{ ...secondaryBtnStyle, flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
              >
                <Upload size={13} /> Upload Logo / Icon…
              </motion.button>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setState((s) => ({ ...s, logoPath: "" }))}
                disabled={!state.logoPath}
                style={dangerBtnStyle}
              >
                Clear
              </motion.button>
            </div>
            <div style={{ fontSize: "11px", color: state.logoPath ? "var(--accent)" : "var(--text-muted)", fontWeight: state.logoPath ? 700 : 400 }}>
              {state.logoPath ? `✓ Logo: ${state.logoPath.split(/[\\/]/).pop()}` : "No logo uploaded"}
            </div>

            {state.logoPath && (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", background: "var(--bg)", padding: "10px", borderRadius: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
                  <span>Logo Scale</span>
                  <span className="tabular-nums" style={{ fontWeight: 700, color: "var(--accent)" }}>{state.logoScale}%</span>
                </div>
                <input
                  type="range"
                  min="20"
                  max="250"
                  value={state.logoScale}
                  onChange={(e) => setState((s) => ({ ...s, logoScale: Number(e.target.value) }))}
                />

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
                  <span>Logo Opacity</span>
                  <span className="tabular-nums" style={{ fontWeight: 700, color: "var(--accent)" }}>{state.logoOpacity}%</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={state.logoOpacity}
                  onChange={(e) => setState((s) => ({ ...s, logoOpacity: Number(e.target.value) }))}
                />

                <div style={{ display: "flex", gap: "8px" }}>
                  <div style={{ flex: 1 }}>
                    <div className="tabular-nums" style={{ fontSize: "11px", marginBottom: "4px" }}>Logo X: {state.logoPosX}%</div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={state.logoPosX}
                      onChange={(e) => setState((s) => ({ ...s, logoPosX: Number(e.target.value) }))}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div className="tabular-nums" style={{ fontSize: "11px", marginBottom: "4px" }}>Logo Y: {state.logoPosY}%</div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={state.logoPosY}
                      onChange={(e) => setState((s) => ({ ...s, logoPosY: Number(e.target.value) }))}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Text Section */}
            <label style={fieldLabelStyle}>Watermark Text (leave empty for none)</label>
            <input
              type="text"
              placeholder="e.g. 100% TRANSPARENT"
              value={state.text}
              onChange={(e) => setState((s) => ({ ...s, text: e.target.value }))}
            />

            <div style={{ display: "flex", gap: "8px" }}>
              <div style={{ flex: 1 }}>
                <div className="tabular-nums" style={{ fontSize: "11px", marginBottom: "4px", color: "var(--text-sec)" }}>Text X: {state.textPosX}%</div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={state.textPosX}
                  onChange={(e) => setState((s) => ({ ...s, textPosX: Number(e.target.value) }))}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div className="tabular-nums" style={{ fontSize: "11px", marginBottom: "4px", color: "var(--text-sec)" }}>Text Y: {state.textPosY}%</div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={state.textPosY}
                  onChange={(e) => setState((s) => ({ ...s, textPosY: Number(e.target.value) }))}
                />
              </div>
            </div>

            <label style={fieldLabelStyle}>Text Fill Color</label>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="color"
                value={state.textColor}
                onChange={(e) => setState((s) => ({ ...s, textColor: e.target.value }))}
                style={{ width: "42px", height: "30px", border: "none", borderRadius: "6px", cursor: "pointer" }}
              />
              {["#FFFFFF", "#0F172A", "#FACC15"].map((c, i) => {
                const label = ["White", "Black", "Yellow"][i];
                const isActive = state.textColor.toUpperCase() === c.toUpperCase();
                return (
                  <motion.button
                    key={c}
                    whileHover={{ y: -0.5 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => setState((s) => ({ ...s, textColor: c }))}
                    style={{
                      ...chipStyle,
                      background: isActive ? "var(--chip-active)" : "var(--chip-bg)",
                      color: isActive ? "var(--chip-active-text)" : "var(--text-sec)",
                    }}
                  >
                    {label}
                  </motion.button>
                );
              })}
            </div>

            {/* Custom Font File */}
            <label style={fieldLabelStyle}>Typography & Custom Font (.ttf, .otf, .woff)</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleBrowseFont}
                style={{ ...secondaryBtnStyle, flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
              >
                <Type size={13} /> Browse Font File…
              </motion.button>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setState((s) => ({ ...s, fontPath: "" }))}
                disabled={!state.fontPath}
                style={dangerBtnStyle}
              >
                Reset Font
              </motion.button>
            </div>
            <div style={{ fontSize: "11px", color: state.fontPath ? "var(--accent)" : "var(--text-muted)", fontWeight: state.fontPath ? 700 : 400 }}>
              {state.fontPath ? `✓ Custom Font: ${state.fontPath.split(/[\\/]/).pop()}` : "Font: System Default Bold"}
            </div>

            {/* Font Scale & Opacity */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
              <span>Font Size Scale</span>
              <span className="tabular-nums" style={{ fontWeight: 700, color: "var(--accent)" }}>{state.fontScale}%</span>
            </div>
            <input
              type="range"
              min="50"
              max="180"
              value={state.fontScale}
              onChange={(e) => setState((s) => ({ ...s, fontScale: Number(e.target.value) }))}
            />

            <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={state.hasOutline}
                onChange={(e) => setState((s) => ({ ...s, hasOutline: e.target.checked }))}
              />
              Add Outline / Stroke to Text
            </label>

            {state.hasOutline && (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="color"
                    value={state.outlineColor}
                    onChange={(e) => setState((s) => ({ ...s, outlineColor: e.target.value }))}
                    style={{ width: "36px", height: "26px", border: "none", borderRadius: "4px", cursor: "pointer" }}
                  />
                  {["#000000", "#FFFFFF", "#334155"].map((c, i) => {
                    const label = ["Black", "White", "Dark Gray"][i];
                    const isActive = state.outlineColor.toUpperCase() === c.toUpperCase();
                    return (
                      <motion.button
                        key={c}
                        whileHover={{ y: -0.5 }}
                        whileTap={{ scale: 0.97 }}
                        onClick={() => setState((s) => ({ ...s, outlineColor: c }))}
                        style={{
                          ...chipStyle,
                          background: isActive ? "var(--chip-active)" : "var(--chip-bg)",
                          color: isActive ? "var(--chip-active-text)" : "var(--text-sec)",
                        }}
                      >
                        {label}
                      </motion.button>
                    );
                  })}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
                  <span>Outline Thickness</span>
                  <span style={{ fontWeight: 700, color: "var(--accent)" }}>
                    {["Thin", "Normal", "Medium", "Thick", "Extra Bold"][state.outlineThickness - 1]}
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={state.outlineThickness}
                  onChange={(e) => setState((s) => ({ ...s, outlineThickness: Number(e.target.value) }))}
                />
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
              <span>Text Opacity</span>
              <span className="tabular-nums" style={{ fontWeight: 700, color: "var(--accent)" }}>{state.opacity}%</span>
            </div>
            <input
              type="range"
              min="10"
              max="100"
              value={state.opacity}
              onChange={(e) => setState((s) => ({ ...s, opacity: Number(e.target.value) }))}
            />
          </div>

          {/* CARD 4: Process Previews */}
          <div style={cardStyle}>
            <div style={cardTitleStyle}>
              <Box size={15} color="var(--accent)" /> 4 · Process Previews
            </div>

            <motion.button
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.975 }}
              onClick={handleStartBatch}
              disabled={isProcessing || !state.inputFolder}
              style={{
                ...primaryBtnStyle,
                opacity: isProcessing || !state.inputFolder ? 0.6 : 1,
              }}
            >
              Generate All JPG Previews
            </motion.button>

            {isProcessing && (
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleCancelBatch}
                style={dangerBtnStyle}
              >
                Cancel Processing
              </motion.button>
            )}

            {isProcessing && (
              <div style={{ width: "100%", height: "7px", background: "var(--slider-track)", borderRadius: "4px", overflow: "hidden" }}>
                <motion.div
                  style={{ height: "100%", background: "var(--accent)" }}
                  initial={{ width: "0%" }}
                  animate={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }}
                  transition={{ ease: "easeOut", duration: 0.2 }}
                />
              </div>
            )}

            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "4px" }}>
              <span className="tabular-nums" style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", background: "var(--success-bg)", color: "var(--success-fg)", borderRadius: "6px" }}>
                {stats.success} Success
              </span>
              <span className="tabular-nums" style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", background: "var(--fail-bg)", color: "var(--fail-fg)", borderRadius: "6px" }}>
                {stats.failed} Failed
              </span>
              <span className="tabular-nums" style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", background: "var(--chip-bg)", color: "var(--text-sec)", borderRadius: "6px" }}>
                {fileList.length} Total
              </span>
            </div>

            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{progress.message}</div>
            {batchErrors.length > 0 && (
              <div style={{ marginTop: "6px", maxHeight: "80px", overflowY: "auto", fontSize: "11px", color: "#EF4444", background: "rgba(239, 68, 68, 0.08)", padding: "6px 10px", borderRadius: "6px" }}>
                {batchErrors.slice(0, 5).map((err, i) => (
                  <div key={i} style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>• {err}</div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT COLUMN: Live Preview Viewport ── */}
        <div style={{ ...cardStyle, flex: 1, display: "flex", flexDirection: "column", padding: "16px", overflow: "hidden" }}>
          {/* Viewport Toolbar */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>Live Preview</span>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                disabled={currentIdx <= 0}
                onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
                style={{ ...chipStyle, display: "flex", alignItems: "center", gap: "4px", opacity: currentIdx <= 0 ? 0.35 : 1 }}
              >
                <ChevronLeft size={13} /> Prev
              </motion.button>
              <span className="tabular-nums" style={{ fontSize: "11px", fontWeight: 700, padding: "3px 8px", background: "var(--chip-bg)", color: "var(--accent)", borderRadius: "6px" }}>
                {fileList.length > 0 ? `${currentIdx + 1} / ${fileList.length}` : "0 / 0"}
              </span>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                disabled={currentIdx >= fileList.length - 1}
                onClick={() => setCurrentIdx((i) => Math.min(fileList.length - 1, i + 1))}
                style={{ ...chipStyle, display: "flex", alignItems: "center", gap: "4px", opacity: currentIdx >= fileList.length - 1 ? 0.35 : 1 }}
              >
                Next <ChevronRight size={13} />
              </motion.button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setFitToView(!fitToView)}
                style={{ ...secondaryBtnStyle, display: "flex", alignItems: "center", gap: "6px" }}
              >
                <Maximize2 size={12} /> {fitToView ? "Fit to View" : "Original 100%"}
              </motion.button>
              <motion.button
                whileHover={{ y: -0.5 }}
                whileTap={{ scale: 0.97 }}
                onClick={async () => {
                  if (!activeFile) return;
                  setIsLoadingPreview(true);
                  try {
                    const api = await ApiBridge.getApi(3000);
                    if (api) {
                      const res = await api.render_preview(activeFile.path, state);
                      if (res && "value" in res && res.value) {
                        setPreviewDataUrl(res.value.dataUrl);
                        setPreviewMeta({ width: res.value.width || 0, height: res.value.height || 0, name: activeFile.name });
                        setRenderError(null);
                      } else if (res && "error" in res && res.error) {
                        setRenderError(res.error);
                      }
                    }
                  } catch (err: unknown) {
                    setRenderError(err instanceof Error ? err.message : "Refresh failed");
                  } finally {
                    setIsLoadingPreview(false);
                  }
                }}
                style={secondaryBtnStyle}
              >
                <RefreshCw size={12} /> Refresh
              </motion.button>
            </div>
          </div>

          {/* 3D Orbit Control Floating HUD */}
          <AnimatePresence>
            {isCurrent3D && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={springTransition}
                style={{
                  background: "var(--hud-bg)",
                  backdropFilter: "blur(14px)",
                  WebkitBackdropFilter: "blur(14px)",
                  border: "1px solid var(--hud-border)",
                  borderRadius: "10px",
                  padding: "8px 12px",
                  marginBottom: "12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.08)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--accent)" }}>
                    🎮 3D 360° Orbit: Drag canvas or pick preset:
                  </span>
                  <div style={{ display: "flex", gap: "4px" }}>
                    {[
                      { name: "Isometric 3/4", y: 45, p: 30 },
                      { name: "Front", y: 0, p: 0 },
                      { name: "Side", y: 90, p: 0 },
                      { name: "Top", y: 0, p: 85 },
                      { name: "Back", y: 180, p: 0 },
                    ].map((item) => {
                      const isActive = active3DPreset === item.name;
                      return (
                        <motion.button
                          key={item.name}
                          whileHover={{ y: -0.5 }}
                          whileTap={{ scale: 0.97 }}
                          onClick={() => {
                            setState((s) => ({ ...s, yaw: item.y, pitch: item.p }));
                            setActive3DPreset(item.name);
                          }}
                          style={{
                            ...chipStyle,
                            position: "relative",
                            background: isActive ? "var(--chip-active)" : "var(--chip-bg)",
                            color: isActive ? "var(--chip-active-text)" : "var(--text-sec)",
                          }}
                        >
                          {isActive && (
                            <motion.div
                              layoutId="activePresetPill"
                              transition={springTransition}
                              style={{
                                position: "absolute",
                                inset: 0,
                                background: "var(--accent)",
                                borderRadius: "var(--radius-chip)",
                                zIndex: -1,
                              }}
                            />
                          )}
                          {item.name}
                        </motion.button>
                      );
                    })}
                  </div>
                </div>

                <div style={{ display: "flex", gap: "16px" }}>
                  <div style={{ flex: 1, display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="tabular-nums" style={{ fontSize: "11px", width: "70px" }}>Yaw: {state.yaw}°</span>
                    <input
                      type="range"
                      min="0"
                      max="360"
                      value={state.yaw}
                      onChange={(e) => {
                        setState((s) => ({ ...s, yaw: Number(e.target.value) }));
                        setActive3DPreset("Custom");
                      }}
                    />
                  </div>
                  <div style={{ flex: 1, display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="tabular-nums" style={{ fontSize: "11px", width: "70px" }}>Pitch: {state.pitch}°</span>
                    <input
                      type="range"
                      min="-85"
                      max="85"
                      value={state.pitch}
                      onChange={(e) => {
                        setState((s) => ({ ...s, pitch: Number(e.target.value) }));
                        setActive3DPreset("Custom");
                      }}
                    />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Canvas Viewport with Interior Depth Shadow & Kinetic Cursor */}
          <div
            onMouseDown={handleMouseDown3D}
            onMouseMove={handleMouseMove3D}
            onMouseUp={handleMouseUp3D}
            style={{
              flex: 1,
              background: "var(--preview-bg)",
              border: "1px solid var(--preview-border)",
              boxShadow: "var(--viewport-shadow)",
              borderRadius: "10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "auto",
              position: "relative",
              cursor: isCurrent3D ? (is3DDragging ? "grabbing" : "grab") : "default",
            }}
          >
            {renderError ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", color: "#EF4444", padding: "20px", textAlign: "center", maxWidth: "420px" }}>
                <span style={{ fontSize: "13px", fontWeight: 700 }}>Unable to Render Preview</span>
                <span style={{ fontSize: "11px", opacity: 0.85, wordBreak: "break-word" }}>{renderError}</span>
              </div>
            ) : previewDataUrl ? (
              <img
                src={previewDataUrl}
                alt="Live Preview"
                style={{
                  maxWidth: fitToView ? "95%" : "none",
                  maxHeight: fitToView ? "95%" : "none",
                  objectFit: "contain",
                  boxShadow: "0 6px 20px rgba(0,0,0,0.18)",
                  borderRadius: "4px",
                  transition: "transform 0.1s var(--spring-transition)",
                }}
              />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", color: "var(--text-muted)" }}>
                <ImageIcon size={34} opacity={0.4} />
                <span style={{ fontSize: "12px" }}>Select an input folder to view preview</span>
              </div>
            )}
          </div>

          {/* Bottom Information Row with Tabular Typography */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "10px", fontSize: "11px", color: "var(--text-sec)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
              {activeFile ? (
                <>
                  <span>Preview: {activeFile.name}</span>
                  <span style={{ padding: "2px 6px", background: "var(--chip-bg)", color: "var(--accent)", borderRadius: "4px" }}>
                    {activeFile.ext.toUpperCase()}
                  </span>
                </>
              ) : (
                <span>No file loaded</span>
              )}
            </div>
            <div className="tabular-nums">
              {previewMeta.width > 0 && `${previewMeta.width} × ${previewMeta.height} px`}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Inline Style Helpers using Apple Depth Tokens
const cardStyle: React.CSSProperties = {
  background: "var(--card-bg)",
  border: "1px solid var(--card-border)",
  boxShadow: "var(--card-shadow)",
  borderRadius: "var(--radius-card)",
  padding: "16px",
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const cardTitleStyle: React.CSSProperties = {
  fontSize: "12px",
  fontWeight: 700,
  letterSpacing: "-0.15px",
  display: "flex",
  alignItems: "center",
  gap: "6px",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "11px",
  fontWeight: 600,
  color: "var(--text-sec)",
};

const secondaryBtnStyle: React.CSSProperties = {
  background: "var(--card-bg)",
  color: "var(--text)",
  border: "1px solid var(--card-border)",
  boxShadow: "var(--btn-shadow)",
  borderRadius: "var(--radius-btn)",
  padding: "7px 12px",
  fontSize: "12px",
  fontWeight: 500,
  cursor: "pointer",
};

const primaryBtnStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "#FFFFFF",
  border: "none",
  boxShadow: "var(--primary-btn-shadow)",
  borderRadius: "var(--radius-btn)",
  padding: "11px 18px",
  fontSize: "13px",
  fontWeight: 600,
  cursor: "pointer",
  width: "100%",
};

const dangerBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--danger)",
  border: "1px solid var(--danger)",
  borderRadius: "var(--radius-btn)",
  padding: "7px 12px",
  fontSize: "12px",
  fontWeight: 500,
  cursor: "pointer",
};

const chipStyle: React.CSSProperties = {
  background: "var(--chip-bg)",
  color: "var(--text-sec)",
  border: "1px solid var(--chip-border)",
  borderRadius: "var(--radius-chip)",
  padding: "4px 8px",
  fontSize: "11px",
  fontWeight: 600,
  cursor: "pointer",
};
