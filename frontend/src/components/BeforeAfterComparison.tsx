import { useEffect, useState } from "react";
import "./beforeAfterComparison.css";

interface Props {
  sourceUrl: string;
  previewUrl: string;
  name: string;
  onClose: () => void;
}

export function BeforeAfterComparison({ sourceUrl, previewUrl, name, onClose }: Props) {
  const [split, setSplit] = useState(50);
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => { setSplit(50); setImageFailed(false); }, [sourceUrl, previewUrl]);

  if (imageFailed) return <div className="compare-unavailable" role="alert">
    <strong>Comparison image unavailable</strong>
    <p>Try switching the comparison off and on again.</p>
    <button className="button" type="button" onClick={onClose}>Return to preview</button>
  </div>;

  return <div className="compare-root" role="group" aria-label={`Source versus Preview: ${name}`}>
    <div className="compare-images">
      <img className="compare-image" src={previewUrl} alt="After: PreviewGen JPG presentation"
        draggable={false} onError={() => setImageFailed(true)} />
      <div className="compare-source-mask" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
        <img className="compare-image" src={sourceUrl} alt="Before: source artwork visualization"
          draggable={false} onError={() => setImageFailed(true)} />
      </div>
      <div className="compare-divider" aria-hidden="true" style={{ left: `${split}%` }}>
        <span className="compare-grip">⇄</span>
      </div>
      <span className="compare-tag compare-tag-before">Source</span>
      <span className="compare-tag compare-tag-after">JPG preview</span>
      <input className="compare-range" type="range" min={0} max={100} step={1}
        value={split} aria-label="Reveal original source versus JPG preview"
        aria-valuetext={`${split}% source visualization visible`}
        onChange={(event) => setSplit(Number(event.target.value))} />
    </div>
    <span className="compare-percentage" role="status">{split}% source · {100 - split}% preview</span>
  </div>;
}
