import React from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";

interface BatchProgressProps {
  isProcessing: boolean;
  progress: { current: number; total: number; message: string };
  stats: { success: number; failed: number };
  batchErrors: string[];
  onStartBatch: () => void;
  onCancelBatch: () => void;
  canStart: boolean;
  truncated?: boolean;
  truncationReasons?: string[];
  discovered?: number;
}

export const BatchProgress: React.FC<BatchProgressProps> = ({
  isProcessing, progress, stats, batchErrors, onStartBatch, onCancelBatch,
  canStart, truncated = false, truncationReasons = [], discovered = 0,
}) => {
  const percent = progress.total > 0
    ? Math.min(100, Math.max(0, Math.round(progress.current / progress.total * 100)))
    : 0;
  return (
    <div className="batch-progress">
      <div className="bp-head">
        <span className="bp-title">Batch export</span>
        {isProcessing
          ? <button type="button" className="button" onClick={onCancelBatch}>Cancel Batch</button>
          : <button type="button" className="button primary" onClick={onStartBatch} disabled={!canStart}>Generate Previews</button>}
      </div>
      {isProcessing && <div className="bp-body">
        <div className="bp-row"><span>{progress.message}</span><span className="bp-percent">{percent}%</span></div>
        <div className="bp-track" role="progressbar" aria-label="Batch generation progress"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.total > 0 ? percent : undefined}>
          <div className="bp-fill" style={{ width: `${percent}%` }} />
        </div>
      </div>}
      {!isProcessing && <p className="muted batch-result" role="status">{progress.message}</p>}
      {!isProcessing && (stats.success > 0 || stats.failed > 0) &&
        <div className="bp-stats">
          <span className="bp-stat ok"><CheckCircle2 size={16}/>{stats.success} saved</span>
          {stats.failed > 0 && <span className="bp-stat bad"><AlertTriangle size={16}/>{stats.failed} failed</span>}
        </div>}
      {!isProcessing && truncated && <div className="bp-truncation" data-testid="batch-truncation-warning">
        <AlertTriangle size={16}/>
        <span>Truncated ({truncationReasons.join(", ") || "safety limit"}) — {stats.success} processed of{" "}
          {discovered || progress.total} discovered. Acknowledge to continue.</span>
      </div>}
      {batchErrors.length > 0 && <div className="bp-errors" role="alert">
        {batchErrors.map((error, i) => <div key={i}>{error}</div>)}
      </div>}
    </div>
  );
};
