import { useRef, type KeyboardEvent, type PointerEvent } from "react";

interface PaneResizerProps {
  label: string;
  value: number;
  min: number;
  max: number;
  reverse?: boolean;
  initial: number;
  onChange: (value: number) => void;
}

/** Native-feeling adjustable separator with keyboard and pointer input. */
export function PaneResizer({ label, value, min, max, reverse = false, initial, onChange }: PaneResizerProps) {
  const drag = useRef<{ startX: number; startValue: number } | null>(null);
  const clamp = (next: number) => Math.max(min, Math.min(max, Math.round(next)));
  const direction = reverse ? -1 : 1;

  const onDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    drag.current = { startX: event.clientX, startValue: value };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current) onChange(clamp(drag.current.startValue + (event.clientX - drag.current.startX) * direction));
  };
  const onUp = (event: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    let next: number;
    switch (event.key) {
      case "ArrowRight": next = value + 16 * direction; break;
      case "ArrowLeft": next = value - 16 * direction; break;
      case "Home": next = min; break;
      case "End": next = max; break;
      default: return;
    }
    event.preventDefault();
    onChange(clamp(next));
  };
  return <div className="pane-resizer" tabIndex={0} role="separator" aria-label={label}
    aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
    title="Drag to resize · Left/Right arrows · Double-click to reset"
    onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
    onLostPointerCapture={() => { drag.current = null; }} onKeyDown={onKey}
    onDoubleClick={() => onChange(initial)} />;
}
