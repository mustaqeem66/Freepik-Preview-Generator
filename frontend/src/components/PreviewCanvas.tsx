import React from "react";
import { Loader2 } from "lucide-react";

interface PreviewCanvasProps {
  previewDataUrl: string | null;
  isLoading: boolean;
  renderError: string | null;
  name: string;
  width: number;
  height: number;
}

export const PreviewCanvas: React.FC<PreviewCanvasProps> = ({
  previewDataUrl,
  isLoading,
  renderError,
  name,
  width,
  height,
}) => {
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        background: "var(--preview-bg)",
        borderRadius: "12px",
        border: "1px solid var(--card-border)",
      }}
    >
      {isLoading && (
        <div
          style={{
            position: "absolute",
            zIndex: 10,
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "8px 16px",
            background: "rgba(0, 0, 0, 0.75)",
            color: "#FFFFFF",
            borderRadius: "20px",
            fontSize: "12px",
          }}
        >
          <Loader2 size={16} className="animate-spin" />
          Rendering preview…
        </div>
      )}

      {renderError && (
        <div
          style={{
            padding: "16px 20px",
            background: "var(--error-bg, rgba(239, 68, 68, 0.1))",
            color: "var(--error, #EF4444)",
            border: "1px solid var(--error, #EF4444)",
            borderRadius: "8px",
            fontSize: "13px",
            maxWidth: "80%",
            textAlign: "center",
          }}
        >
          <strong>Preview Error:</strong> {renderError}
        </div>
      )}

      {!renderError && previewDataUrl && (
        <img
          src={previewDataUrl}
          alt={name || "Preview"}
          style={{
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
            boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            borderRadius: "6px",
          }}
        />
      )}

      {!renderError && !previewDataUrl && !isLoading && (
        <div style={{ color: "var(--text-sec)", fontSize: "13px" }}>
          Select an asset to view preview
        </div>
      )}

      {name && (
        <div
          style={{
            position: "absolute",
            bottom: "12px",
            left: "14px",
            padding: "4px 10px",
            background: "rgba(0,0,0,0.6)",
            color: "#FFF",
            borderRadius: "6px",
            fontSize: "11px",
            backdropFilter: "blur(4px)",
          }}
        >
          {name} {width > 0 && height > 0 ? `(${width} × ${height})` : ""}
        </div>
      )}
    </div>
  );
};
