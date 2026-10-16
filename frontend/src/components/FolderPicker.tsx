import React from "react";
import { FolderOpen } from "lucide-react";

interface FolderPickerProps {
  inputFolder: string;
  outputFolder: string;
  sameFolder: boolean;
  onBrowseInput: () => void;
  onBrowseOutput: () => void;
  onToggleSameFolder: (checked: boolean) => void;
}

export const FolderPicker: React.FC<FolderPickerProps> = ({
  inputFolder,
  outputFolder,
  sameFolder,
  onBrowseInput,
  onBrowseOutput,
  onToggleSameFolder,
}) => {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <button
          type="button"
          onClick={onBrowseInput}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 14px",
            background: "var(--accent)",
            color: "#FFFFFF",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "13px",
          }}
        >
          <FolderOpen size={16} />
          Choose Input Folder
        </button>
        <span
          style={{
            fontSize: "12px",
            color: "var(--text-sec)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: "350px",
          }}
          title={inputFolder || "No folder selected"}
        >
          {inputFolder || "No folder selected"}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <button
          type="button"
          onClick={onBrowseOutput}
          disabled={sameFolder}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 14px",
            background: sameFolder ? "var(--btn-disabled)" : "var(--surface)",
            color: "var(--text-main)",
            border: "1px solid var(--card-border)",
            borderRadius: "8px",
            cursor: sameFolder ? "not-allowed" : "pointer",
            fontWeight: 600,
            fontSize: "13px",
            opacity: sameFolder ? 0.6 : 1.0,
          }}
        >
          <FolderOpen size={16} />
          Choose Output Folder
        </button>
        <span
          style={{
            fontSize: "12px",
            color: "var(--text-sec)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: "280px",
          }}
          title={sameFolder ? "Saving alongside source" : outputFolder || "Defaults to input folder"}
        >
          {sameFolder ? "Saving alongside source" : outputFolder || "Defaults to input folder"}
        </span>
        <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", cursor: "pointer", marginLeft: "8px" }}>
          <input
            type="checkbox"
            checked={sameFolder}
            onChange={(e) => onToggleSameFolder(e.target.checked)}
          />
          Same as input
        </label>
      </div>
    </div>
  );
};
