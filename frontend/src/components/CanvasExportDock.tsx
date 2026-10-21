import { FolderOpen } from "lucide-react";
import { BatchProgress, type BatchProgressProps } from "./BatchProgress";

type Props = BatchProgressProps & {
  canOpenOutput: boolean;
  onOpenOutput: () => void;
};

/** Scoped action dock: keeps output commands attached to the preview pane. */
export function CanvasExportDock({ canOpenOutput, onOpenOutput, ...batchProps }: Props) {
  return <div className="canvas-export-dock" role="region" aria-label="Batch export actions">
    <BatchProgress {...batchProps} />
    <button type="button" className="button dock-open-output" aria-label="Open output folder"
      disabled={!canOpenOutput} onClick={onOpenOutput}>
      <FolderOpen size={15} aria-hidden="true" />Open output
    </button>
  </div>;
}
