import { useState } from "react";
import type { PreviewState } from "../types";
import {
  dropStylePreset, putStylePreset, readStylePresets,
  writeStylePresets,
} from "../brandPresets";

interface StylePresetManagerProps {
  state: PreviewState;
  onChange: (patch: Partial<PreviewState>) => void;
}

/** Local appearance settings only: file grants, paths and outputs are excluded. */
export function StylePresetManager({ state, onChange }: StylePresetManagerProps) {
  const [presets, setPresets] = useState(readStylePresets);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const current = presets.find(p => p.name === selected);

  const save = () => {
    try {
      const next = putStylePreset(presets, name, state);
      writeStylePresets(next);
      setPresets(next);
      const named = next.find(
        p => p.name.toLocaleLowerCase("en") === name.trim().toLocaleLowerCase("en")
      );
      setSelected(named?.name || "");
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Cannot save style preset.");
    }
  };
  const remove = () => {
    if (!current) return;
    try {
      const next = dropStylePreset(presets, current.name);
      writeStylePresets(next);
      setPresets(next);
      setSelected("");
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Cannot delete style preset.");
    }
  };

  return <section className="inspector-section">
    <div className="section-heading"><h2>Style presets</h2></div>
    <p className="muted">Save watermark, background, framing, camera and layout settings for later. Logo/font files and folder permissions are never stored or restored.</p>
    <label className="field-label">Preset name
      <input aria-label="Style preset name" maxLength={40} value={name}
        placeholder="e.g. Marketplace clean"
        onChange={(event) => setName(event.target.value)} />
    </label>
    <div className="file-control">
      <button type="button" className="button" disabled={!name.trim()} onClick={save}>
        Save style
      </button>
    </div>
    <label className="field-label">Saved style
      <select aria-label="Saved style preset" value={selected}
        onChange={(event) => setSelected(event.target.value)}>
        <option value="">Choose style…</option>
        {presets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
      </select>
    </label>
    <div className="file-control">
      <button type="button" className="button" disabled={!current}
        onClick={() => { if (current) { onChange(current.styles); setError(""); } }}>
        Apply style
      </button>
      <button type="button" className="button" disabled={!current} onClick={remove}>
        Delete style
      </button>
    </div>
    {error && <p role="alert" className="muted">{error}</p>}
  </section>;
}
