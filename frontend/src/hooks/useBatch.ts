import { useState, useEffect, useCallback, useRef } from "react";
import { BatchStatus, BatchSummary, PreviewState } from "../types";
import { ApiBridge, bridgeEvents } from "../api/bridge";

// A cancelled batch must emit batch.finished (the backend always terminates a
// render budget); this backstops a lost terminal envelope so the UI never
// sits in "Cancelling…" or "generating" forever.
const CANCEL_TERMINAL_DEADLINE_MS = 120_000;

function mapSummaryStatus(summary: BatchSummary): BatchStatus {
  if (summary.cancelled || summary.status === "cancelled") return "cancelled";
  switch (summary.status) {
    case "completed_with_warnings":
      return "completed-with-warnings";
    case "completed_with_errors":
      return "completed-with-errors";
    case "failed":
      return "failed";
    case "completed":
      return "completed";
    default:
      break;
  }
  if (summary.truncated) return "completed-with-warnings";
  if (summary.failed > 0) return "completed-with-errors";
  return "completed";
}

export function useBatch() {
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [batchStatus, setBatchStatus] = useState<BatchStatus>("idle");
  const [progress, setProgress] = useState<{ current: number; total: number; message: string }>({
    current: 0,
    total: 0,
    message: "Ready to process",
  });
  const [stats, setStats] = useState<{ success: number; failed: number }>({ success: 0, failed: 0 });
  const [batchErrors, setBatchErrors] = useState<string[]>([]);
  const [truncationReasons, setTruncationReasons] = useState<string[]>([]);
  const [discovered, setDiscovered] = useState<number>(0);
  // A truncated batch requires the operator to explicitly acknowledge that not
  // every file was processed before further generation is allowed.
  const [requiresTruncationAck, setRequiresTruncationAck] = useState<boolean>(false);
  const latestSeqRef = useRef<number>(0);
  const activeOpIdRef = useRef<string | null>(null);
  const isTerminalRef = useRef<boolean>(false);
  const replayRef = useRef<(operationId: string) => void>(() => {});
  const startPendingRef = useRef<boolean>(false);
  const bufferedEventsRef = useRef<Array<{ kind: "progress" | "finished"; payload: any; meta: { operationId?: string; sequence?: number } }>>([]);
  const cancelDeadlineRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (cancelDeadlineRef.current !== null) clearTimeout(cancelDeadlineRef.current);
  }, []);

  useEffect(() => {
    const applyProgress = ({ current, total, message }: { current: number; total: number; message: string }, meta: { operationId?: string; sequence?: number }) => {
      // Reject nonterminal progress events after a terminal event has arrived (Finding 8)
      if (isTerminalRef.current) return;
      if (!activeOpIdRef.current || meta?.operationId !== activeOpIdRef.current) return;
      if (typeof meta?.sequence === "number" && meta.sequence < latestSeqRef.current) return;
      if (typeof meta?.sequence === "number") latestSeqRef.current = meta.sequence;
      // A negative total marks the indeterminate discovery phase.
      setProgress({ current, total: total > 0 ? total : 0, message });
    };

    const applyFinished = (summary: BatchSummary, meta: { operationId?: string; sequence?: number }) => {
      if (!activeOpIdRef.current || meta?.operationId !== activeOpIdRef.current) return;
      if (cancelDeadlineRef.current !== null) {
        clearTimeout(cancelDeadlineRef.current);
        cancelDeadlineRef.current = null;
      }
      isTerminalRef.current = true;
      if (typeof meta?.sequence === "number") latestSeqRef.current = Math.max(latestSeqRef.current, meta.sequence);
      setIsProcessing(false);
      const { success, failed, skipped, errors, duration } = summary;
      const status = mapSummaryStatus(summary);
      const reasons = Array.isArray(summary.truncationReasons) ? summary.truncationReasons : [];

      setBatchStatus(status);
      setTruncationReasons(reasons);
      setDiscovered(typeof summary.discovered === "number" ? summary.discovered : summary.planned || 0);
      setRequiresTruncationAck(summary.truncated === true || status === "completed-with-warnings");

      const message =
        status === "cancelled"
          ? `Cancelled after ${duration}s. (${success} saved, ${failed} failed, ${skipped || 0} skipped)`
          : status === "completed-with-warnings"
            ? `Completed with warnings in ${duration}s: discovery was truncated (${reasons.join(", ") || "unknown"}). ` +
              `${success} previews saved; other files were not processed.`
            : status === "completed-with-errors"
              ? `Completed with issues in ${duration}s: ${success} succeeded, ${failed} failed, ${skipped || 0} skipped.`
              : status === "failed"
                ? "Batch failed. Review the error below."
                : `Completed in ${duration}s! ${success} previews saved (${skipped || 0} skipped).`;

      setProgress({
        current: success + failed + (skipped || 0),
        total: summary.planned || success + failed + (skipped || 0),
        message,
      });
      setStats({ success, failed });
      setBatchErrors(errors && errors.length > 0 ? errors : []);
    };

    const unsubProgress = bridgeEvents.subscribe("batch.progress", (payload, meta) => {
      if (startPendingRef.current) {
        bufferedEventsRef.current.push({ kind: "progress", payload, meta });
        return;
      }
      applyProgress(payload, meta);
    });
    const unsubFinished = bridgeEvents.subscribe("batch.finished", (payload, meta) => {
      if (startPendingRef.current) {
        bufferedEventsRef.current.push({ kind: "finished", payload, meta });
        return;
      }
      applyFinished(payload, meta);
    });
    replayRef.current = (operationId: string) => {
      const buffered = bufferedEventsRef.current;
      bufferedEventsRef.current = [];
      for (const entry of buffered) {
        if (entry.meta.operationId !== operationId) continue;
        if (entry.kind === "progress") applyProgress(entry.payload, entry.meta);
        else applyFinished(entry.payload, entry.meta);
      }
    };

    return () => {
      unsubProgress();
      unsubFinished();
    };
  }, []);

  const acknowledgeTruncation = useCallback(() => {
    setRequiresTruncationAck(false);
  }, []);

  const startBatch = useCallback(
    async (inputFolder: string, outputFolder: string, totalFiles: number, config: PreviewState) => {
      if (!inputFolder) return;
      setIsProcessing(true);
      setBatchStatus("generating");
      setStats({ success: 0, failed: 0 });
      setBatchErrors([]);
      setTruncationReasons([]);
      latestSeqRef.current = 0;
      isTerminalRef.current = false;
      activeOpIdRef.current = null;
      startPendingRef.current = true;
      bufferedEventsRef.current = [];
      if (cancelDeadlineRef.current !== null) {
        clearTimeout(cancelDeadlineRef.current);
        cancelDeadlineRef.current = null;
      }
      setRequiresTruncationAck(false);
      setProgress({ current: 0, total: totalFiles, message: "Starting batch generation…" });

      try {
        const api = await ApiBridge.getApi(3000);
        if (!api) throw new Error("Backend unavailable. Reconnect before generating previews.");
        const response = await api.start_batch(inputFolder, config.sameFolder ? inputFolder : outputFolder || inputFolder, config);
        if (!response?.ok || !response.operationId) throw new Error(response?.error || "Unable to start batch");
        activeOpIdRef.current = response.operationId;
        startPendingRef.current = false;
        replayRef.current(response.operationId);
      } catch (err) {
        startPendingRef.current = false;
        bufferedEventsRef.current = [];
        setIsProcessing(false);
        setBatchStatus("failed");
        setBatchErrors([err instanceof Error ? err.message : "Failed to start batch"]);
      }
    },
    []
  );

  const cancelBatch = useCallback(async () => {
    setBatchStatus("batch-cancelling");
    if (cancelDeadlineRef.current !== null) clearTimeout(cancelDeadlineRef.current);
    // Even if the cancel request itself fails to reach the backend, the
    // deadline keeps the UI honest: a late batch.finished still clears it.
    cancelDeadlineRef.current = setTimeout(() => {
      cancelDeadlineRef.current = null;
      if (isTerminalRef.current) return;
      isTerminalRef.current = true;
      activeOpIdRef.current = null;
      setIsProcessing(false);
      setBatchStatus("failed");
      setProgress((prev) => ({ ...prev, message: "Cancellation timed out — no completion event arrived from the backend." }));
    }, CANCEL_TERMINAL_DEADLINE_MS);
    try {
      const api = await ApiBridge.getApi(3000);
      if (!api) throw new Error("Backend unavailable. The batch cancellation was not delivered.");
      await api.cancel_batch();
    } catch (error) {
      if (cancelDeadlineRef.current !== null) {
        clearTimeout(cancelDeadlineRef.current);
        cancelDeadlineRef.current = null;
      }
      setBatchStatus("generating");
      setBatchErrors([error instanceof Error ? error.message : "Could not cancel the batch"]);
    }
  }, []);

  return {
    isProcessing,
    batchStatus,
    progress,
    stats,
    batchErrors,
    truncationReasons,
    discovered,
    requiresTruncationAck,
    acknowledgeTruncation,
    startBatch,
    cancelBatch,
  };
}
