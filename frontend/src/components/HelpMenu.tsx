import { useEffect, useRef, useState } from "react";
import { CircleHelp, FolderSearch, X } from "lucide-react";

interface HelpMenuProps {
  onOpenDiagnostics: () => void;
  disabled?: boolean;
}

export function HelpMenu({ onOpenDiagnostics, disabled = false }: HelpMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const close = () => {
    setOpen(false);
    toggleRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    closeButtonRef.current?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return <div className="help-menu" ref={rootRef}>
    <button ref={toggleRef} type="button" className="icon-button help-toggle" title="Help and diagnostics"
      aria-label="Help and diagnostics" aria-haspopup="dialog" aria-expanded={open} aria-controls="help-popover"
      onClick={() => setOpen((previous) => !previous)}><CircleHelp size={17} /></button>
    {open && <div className="help-popover" id="help-popover" role="dialog" aria-label="Help and diagnostics">
      <div className="section-heading"><h2>Help</h2><button ref={closeButtonRef} type="button" className="icon-button"
        aria-label="Close help" onClick={close}><X size={15} /></button></div>
      <p className="muted">PreviewGen runs entirely on this computer. Nothing is uploaded.</p>
      <p className="muted">Use ← and → to move between assets. Shift + arrow keys orbit a 3D model.</p>
      <button type="button" className="button" disabled={disabled}
        onClick={() => { close(); onOpenDiagnostics(); }}><FolderSearch size={15} />Open diagnostics folder</button>
    </div>}
  </div>;
}
