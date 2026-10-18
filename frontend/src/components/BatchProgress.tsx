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
  isProcessing,
  progress,
  stats,
  batchErrors,
  onStartBatch,
  onCancelBatch,
  canStart,
  truncated = false,
  truncationReasons = [],
  discovered = 0,
}) => {
  const percent = progress.total > 0 ? Math.min(100, Math.round((progress.current / progress.total) * 100)) : 0;

  return (
    <div
      className="batch-progress"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        padding: "16px",
        background: "var(--card-bg)",
        border: "1px solid var(--card-border)",
        borderRadius: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "13px", fontWeight: 600 }}>Batch export</span>
        {isProcessing ? (
          <button
            type="button"
            onClick={onCancelBatch}
            style={{
              padding: "6px 14px",
              background: "rgba(239, 68, 68, 0.15)",
              color: "#EF4444",
              border: "1px solid #EF4444",
              borderRadius: "8px",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "12px",
            }}
          >
            Cancel Batch
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartBatch}
            disabled={!canStart}
            style={{
              padding: "8px 18px",
              background: canStart ? "var(--accent)" : "var(--btn-disabled)",
              color: "#FFFFFF",
              border: "none",
              borderRadius: "8px",
              fontWeight: 700,
              cursor: canStart ? "pointer" : "not-allowed",
              fontSize: "13px",
              opacity: canStart ? 1.0 : 0.6,
            }}
          >
            Generate Previews
          </button>
        )}
      </div>

      {isProcessing && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "var(--text-sec)" }}>
            <span>{progress.message}</span>
            <span>{percent}%</span>
          </div>
          <div role="progressbar" aria-label="Batch generation progress" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={progress.total > 0 ? percent : undefined}
            style={{ height: "6px", background: "var(--chip-bg)", borderRadius: "3px", overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${percent}%`,
                background: "var(--accent)",
                transition: "width 0.2s ease",
              }}
            />
          </div>
        </div>
      )}

      {!isProcessing && <p className="muted batch-result" role="status">{progress.message}</p>}
      {!isProcessing && (stats.success > 0 || stats.failed > 0) && (
        <div style={{ display: "flex", alignItems: "center", gap: "16px", fontSize: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--success, #10B981)" }}>
            <CheckCircle2 size={16} /> {stats.success} saved
          </div>
          {stats.failed > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--error, #EF4444)" }}>
              <AlertTriangle size={16} /> {stats.failed} failed
            </div>
          )}
        </div>
      )}

      {!isProcessing && truncated && (
        <div
          data-testid="batch-truncation-warning"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "8px 12px",
            background: "rgba(245, 158, 11, 0.12)",
            border: "1px solid rgba(245, 158, 11, 0.35)",
            borderRadius: "6px",
            fontSize: "11px",
            color: "#F59E0B",
          }}
        >
          <AlertTriangle size={16} />
          <span>
            Truncated ({truncationReasons.join(", ") || "safety limit"}) — {stats.success} processed of{" "}
            {discovered || progress.total} discovered. Acknowledge to continue.
          </span>
        </div>
      )}

      {batchErrors.length > 0 && (
        <div
          style={{
            maxHeight: "100px",
            overflowY: "auto",
            padding: "8px 12px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.2)",
            borderRadius: "6px",
            fontSize: "11px",
            color: "#EF4444",
          }}
        >
          {batchErrors.map((err, i) => (
            <div key={i}>{err}</div>
          ))}
        </div>
      )}
    </div>
  );
};
