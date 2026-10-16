import React from "react";
import { PreviewState } from "../types";
import { Type, Sparkles, Box, Image as ImageIcon } from "lucide-react";

interface SettingsPanelProps {
  state: PreviewState;
  onChange: (patch: Partial<PreviewState>) => void;
  onBrowseLogo: () => void;
  onBrowseFont: () => void;
  is3D: boolean;
}

const cardStyle: React.CSSProperties = {
  background: "var(--card-bg)",
  border: "1px solid var(--card-border)",
  borderRadius: "12px",
  padding: "16px",
  display: "flex",
  flexDirection: "column",
  gap: "12px",
};

const cardTitleStyle: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 700,
  letterSpacing: "-0.2px",
  display: "flex",
  alignItems: "center",
  gap: "6px",
  color: "var(--text-main)",
};

const labelStyle: React.CSSProperties = {
  fontSize: "12px",
  fontWeight: 600,
  color: "var(--text-sec)",
  marginBottom: "4px",
  display: "block",
};

export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  state,
  onChange,
  onBrowseLogo,
  onBrowseFont,
  is3D,
}) => {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* CARD 2: Diagonal Background */}
      <div style={cardStyle}>
        <div style={cardTitleStyle}>
          <Sparkles size={15} color="var(--accent)" /> 2 · Diagonal Split & Colors
        </div>

        <div>
          <label style={labelStyle}>Solid Triangle Color</label>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <input
              type="color"
              value={state.solidColor}
              onChange={(e) => onChange({ solidColor: e.target.value })}
              style={{ width: "36px", height: "32px", border: "none", cursor: "pointer", background: "none" }}
            />
            <span style={{ fontSize: "12px", fontFamily: "monospace" }}>{state.solidColor}</span>
          </div>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={state.invertTriangles}
            onChange={(e) => onChange({ invertTriangles: e.target.checked })}
          />
          Invert split (solid left, transparent right)
        </label>

        <div>
          <label style={labelStyle}>Overwrite Export Policy</label>
          <select
            value={state.overwritePolicy || "rename"}
            onChange={(e) => onChange({ overwritePolicy: e.target.value as "rename" | "skip" | "overwrite" })}
            style={{ width: "100%", padding: "6px 10px", borderRadius: "8px", border: "1px solid var(--card-border)" }}
          >
            <option value="rename">Rename if exists (e.g. filename_copy1.jpg) [Recommended]</option>
            <option value="skip">Skip if exists</option>
            <option value="overwrite">Overwrite existing files</option>
          </select>
        </div>
      </div>

      {/* CARD 3: Text Customization */}
      <div style={cardStyle}>
        <div style={cardTitleStyle}>
          <Type size={15} color="var(--accent)" /> 3 · Branding Text
        </div>

        <div>
          <label style={labelStyle}>Banner Text (Max 100 characters)</label>
          <input
            type="text"
            maxLength={100}
            value={state.text}
            onChange={(e) => onChange({ text: e.target.value })}
            style={{ width: "100%", padding: "6px 10px", borderRadius: "8px", border: "1px solid var(--card-border)" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
          <div>
            <label style={labelStyle}>Text Color</label>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="color"
                value={state.textColor}
                onChange={(e) => onChange({ textColor: e.target.value })}
                style={{ width: "32px", height: "28px", border: "none", cursor: "pointer", background: "none" }}
              />
              <span style={{ fontSize: "11px", fontFamily: "monospace" }}>{state.textColor}</span>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Opacity ({state.opacity}%)</label>
            <input
              type="range"
              min={10}
              max={100}
              value={state.opacity}
              onChange={(e) => onChange({ opacity: Number(e.target.value) })}
              style={{ width: "100%" }}
            />
          </div>
        </div>

        <div>
          <label style={labelStyle}>Custom Font (.ttf, .otf, .woff)</label>
          <div style={{ display: "flex", gap: "8px" }}>
            <input
              type="text"
              readOnly
              placeholder="System default (Bold)"
              value={state.fontPath}
              style={{ flex: 1, padding: "6px 8px", borderRadius: "8px", border: "1px solid var(--card-border)", fontSize: "11px" }}
            />
            <button
              type="button"
              onClick={onBrowseFont}
              style={{ padding: "6px 12px", background: "var(--surface)", border: "1px solid var(--card-border)", borderRadius: "8px", fontSize: "11px", cursor: "pointer" }}
            >
              Browse…
            </button>
          </div>
        </div>
      </div>

      {/* CARD 4: Logo Branding */}
      <div style={cardStyle}>
        <div style={cardTitleStyle}>
          <ImageIcon size={15} color="var(--accent)" /> 4 · Brand Logo
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            type="text"
            readOnly
            placeholder="No custom logo chosen"
            value={state.logoPath}
            style={{ flex: 1, padding: "6px 8px", borderRadius: "8px", border: "1px solid var(--card-border)", fontSize: "11px" }}
          />
          <button
            type="button"
            onClick={onBrowseLogo}
            style={{ padding: "6px 12px", background: "var(--surface)", border: "1px solid var(--card-border)", borderRadius: "8px", fontSize: "11px", cursor: "pointer" }}
          >
            Browse…
          </button>
        </div>
      </div>

      {/* CARD 5: 3D Camera Angles */}
      {is3D && (
        <div style={cardStyle}>
          <div style={cardTitleStyle}>
            <Box size={15} color="var(--accent)" /> 5 · 3D Orbit & Elevation
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div>
              <label style={labelStyle}>Yaw Rotation ({Math.round(state.yaw)}°)</label>
              <input
                type="range"
                min={0}
                max={360}
                value={state.yaw}
                onChange={(e) => onChange({ yaw: Number(e.target.value) })}
                style={{ width: "100%" }}
              />
            </div>
            <div>
              <label style={labelStyle}>Pitch Elevation ({Math.round(state.pitch)}°)</label>
              <input
                type="range"
                min={-85}
                max={85}
                value={state.pitch}
                onChange={(e) => onChange({ pitch: Number(e.target.value) })}
                style={{ width: "100%" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
