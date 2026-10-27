import { type CSSProperties } from "react";
import { Box, Image as ImageIcon, Palette, Type, X } from "lucide-react";
import { PreviewState } from "../types";

interface SettingsPanelProps {
  state: PreviewState;
  onChange: (patch: Partial<PreviewState>) => void;
  onBrowseLogo: () => void;
  onBrowseFont: () => void;
  is3D: boolean;
}

function Slider({ label, value, min = 0, max = 100, unit = "%", hints, onChange }: {
  label: string; value: number; min?: number; max?: number; unit?: string;
  hints?: readonly [string, string, string]; onChange: (value: number) => void;
}) {
  // Input remains a real native range control: keyboard, pointer, touch and
  // screen-reader interaction never depend on a custom drag implementation.
  const progress = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  const style = { "--slider-progress": `${progress}%` } as CSSProperties;

  return <label className="slider-field precision-slider">
    <span className="precision-slider-heading"><span>{label}</span><output>{Math.round(value)}{unit}</output></span>
    <span className="precision-slider-track">
      <input type="range" aria-label={label} min={min} max={max} value={value}
        style={style} onChange={(event) => onChange(Number(event.target.value))} />
    </span>
    {hints && <span className="precision-slider-hints" aria-hidden="true">
      <span>{hints[0]}</span><span>{hints[1]}</span><span>{hints[2]}</span>
    </span>}
  </label>;
}

function Color({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="color-field"><span>{label}</span><span className="color-value">
    <input type="color" value={value} onChange={(e) => onChange(e.target.value)} />
    <span>{value.toUpperCase()}</span></span></label>;
}

const CAMERA_VIEWS = [
  { name: "Isometric", yaw: 45, pitch: 30 }, { name: "Front", yaw: 0, pitch: 0 },
  { name: "Side", yaw: 90, pitch: 0 }, { name: "Top", yaw: 0, pitch: 85 },
  { name: "Back", yaw: 180, pitch: 0 },
];
const COLORS = ["#FFFFFF", "#F5F1E9", "#D4D4D8", "#28282C"];

export function SettingsPanel({ state, onChange, onBrowseLogo, onBrowseFont, is3D }: SettingsPanelProps) {
  return <div className="settings-panel">
    <section className="inspector-section">
      <div className="section-heading"><Palette size={16} /><h2>Background</h2></div>
      <div className="segmented" aria-label="Solid background side">
        <button type="button" aria-pressed={state.invertTriangles} onClick={() => onChange({ invertTriangles: true })}>Solid left</button>
        <button type="button" aria-pressed={!state.invertTriangles} onClick={() => onChange({ invertTriangles: false })}>Solid right</button>
      </div>
      <Color label="Solid color" value={state.solidColor} onChange={(solidColor) => onChange({ solidColor })} />
      <div className="color-presets">{COLORS.map((color) => <button key={color} type="button"
        className="color-swatch" style={{ background: color }} aria-label={`Set background ${color}`}
        aria-pressed={state.solidColor.toUpperCase() === color} onClick={() => onChange({ solidColor: color })} />)}</div>
      <p className="muted">The checkerboard demonstrates transparency. JPG exports have an opaque background.</p>
      <label className="check-row"><input type="checkbox" checked={state.animationContactSheet === true}
        onChange={(event) => onChange({ animationContactSheet: event.target.checked })} />Animated GIF/WebP contact sheet</label>
      {state.animationContactSheet === true && <p className="muted">Shows up to nine GIF/WebP frames in one canvas. Other formats and single-frame images are unchanged.</p>}
      <label className="check-row"><input type="checkbox" checked={state.brushsetContactSheet === true}
        onChange={(event) => onChange({ brushsetContactSheet: event.target.checked })} />Procreate brushset contact sheet</label>
      {state.brushsetContactSheet === true && <p className="muted">Opt-in: previews up to nine tips from a selected .brushset.</p>}
      <label className="check-row"><input type="checkbox" checked={state.autoFrame === true}
        onChange={(e) => onChange({ autoFrame: e.target.checked })} />Auto-frame transparent subject</label>
      {state.autoFrame === true && <>
        <Slider label="Subject margin" min={0} max={25} value={state.frameMargin ?? 8} unit="%"
          hints={["Tight", "Balanced", "Spacious"]} onChange={(frameMargin) => onChange({ frameMargin })} />
        <p className="muted">Opt-in: centers the visible subject while retaining the original canvas size and aspect ratio. Can enlarge small artwork.</p>
      </>}
    </section>

    {is3D && <section className="inspector-section">
      <div className="section-heading"><Box size={16} /><h2>3D camera</h2></div>
      <p className="muted">Drag the preview to orbit, or choose a view.</p>
      <div className="camera-presets">{CAMERA_VIEWS.map((view) => <button className="button" type="button" key={view.name}
        aria-pressed={state.yaw === view.yaw && state.pitch === view.pitch}
        onClick={() => onChange({ yaw: view.yaw, pitch: view.pitch })}>{view.name}</button>)}</div>
      <Slider label="Yaw rotation" value={state.yaw} max={360} unit="°" onChange={(yaw) => onChange({ yaw })} />
      <Slider label="Pitch elevation" value={state.pitch} min={-85} max={85} unit="°" onChange={(pitch) => onChange({ pitch })} />
      <Color label="Untextured model color" value={state.modelColor || "#7882A0"} onChange={(modelColor) => onChange({ modelColor })} />
    </section>}

    <section className="inspector-section">
      <div className="section-heading"><Type size={16} /><h2>Watermark</h2></div>
      <label className="field-label">Text<input type="text" maxLength={100} value={state.text}
        placeholder="Leave empty for no text" onChange={(e) => onChange({ text: e.target.value })} /></label>
      <label className="field-label">Watermark placement
        <select aria-label="Watermark placement" value={state.position || "custom"}
          onChange={(e) => onChange({ position: e.target.value as PreviewState["position"] })}>
          <option value="custom">Custom X / Y</option>
          <option value="top-left">Top left</option>
          <option value="top-right">Top right</option>
          <option value="center">Center on artwork</option>
          <option value="bottom-left">Bottom left</option>
          <option value="bottom-right">Bottom right</option>
          <option value="tiled">Tiled diagonal</option>
        </select>
      </label>
      <Color label="Text color" value={state.textColor} onChange={(textColor) => onChange({ textColor })} />
      <Slider label="Text opacity" value={state.opacity} hints={["Subtle", "Balanced", "Opaque"]}
        onChange={(opacity) => onChange({ opacity })} />
      <Slider label="Font scale" value={state.fontScale} min={20} max={300}
        hints={["Smaller", "Standard", "Larger"]} onChange={(fontScale) => onChange({ fontScale })} />
      {(state.position || "custom") === "custom" && <div className="paired-fields">
        <Slider label="Text X" value={state.textPosX} onChange={(textPosX) => onChange({ textPosX })} />
        <Slider label="Text Y" value={state.textPosY} onChange={(textPosY) => onChange({ textPosY })} />
      </div>}
      <label className="check-row"><input type="checkbox" checked={state.hasOutline}
        onChange={(e) => onChange({ hasOutline: e.target.checked })} />Outline</label>
      {state.hasOutline && <>
        <Color label="Outline color" value={state.outlineColor} onChange={(outlineColor) => onChange({ outlineColor })} />
        <Slider label="Outline thickness" value={state.outlineThickness} min={1} max={10} unit="" onChange={(outlineThickness) => onChange({ outlineThickness })} />
      </>}
      <div className="file-control"><span className="path-hint" title={state.fontPath}>{state.fontPath.split(/[\\/]/).pop() || "System font"}</span>
        <button type="button" className="button" onClick={onBrowseFont}>Choose font…</button>
        {state.fontPath && <button type="button" className="icon-button" aria-label="Remove custom font" onClick={() => onChange({ fontPath: "" })}><X size={14} /></button>}
      </div>
    </section>

    <section className="inspector-section">
      <div className="section-heading"><ImageIcon size={16} /><h2>Brand logo</h2></div>
      <div className="file-control"><span className="path-hint" title={state.logoPath}>{state.logoPath.split(/[\\/]/).pop() || "No logo selected"}</span>
        <button type="button" className="button" onClick={onBrowseLogo}>Choose logo…</button>
        {state.logoPath && <button type="button" className="icon-button" aria-label="Remove logo" onClick={() => onChange({ logoPath: "" })}><X size={14} /></button>}
      </div>
      {state.logoPath && <>
        <Slider label="Logo scale" value={state.logoScale} min={20} max={300}
          hints={["Smaller", "Standard", "Larger"]} onChange={(logoScale) => onChange({ logoScale })} />
        <Slider label="Logo opacity" value={state.logoOpacity}
          hints={["Subtle", "Balanced", "Opaque"]} onChange={(logoOpacity) => onChange({ logoOpacity })} />
        <div className="paired-fields">
          <Slider label="Logo X" value={state.logoPosX} onChange={(logoPosX) => onChange({ logoPosX })} />
          <Slider label="Logo Y" value={state.logoPosY} onChange={(logoPosY) => onChange({ logoPosY })} />
        </div>
      </>}
    </section>
    <section className="inspector-section">
      <div className="section-heading"><h2>Desktop notifications</h2></div>
      <label className="check-row"><input type="checkbox" checked={state.desktopNotifications}
        onChange={(e) => onChange({ desktopNotifications: e.target.checked })} />
        Notify when a batch finishes</label>
      <p className="muted">Off by default. Requires notification permissions and a supported system notification service.</p>
    </section>
    <section className="inspector-section">
      <div className="section-heading"><h2>Existing exports</h2></div>
      <label className="field-label">When a JPG already exists<select value={state.overwritePolicy || "rename"}
        onChange={(e) => onChange({ overwritePolicy: e.target.value as "rename" | "skip" | "overwrite" })}>
        <option value="rename">Keep both — add a copy number</option><option value="skip">Skip existing JPGs</option>
        <option value="overwrite">Replace existing JPGs</option>
      </select></label>
    </section>
  </div>;
}
