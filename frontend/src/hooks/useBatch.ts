import { useState, useEffect, useCallback } from "react";
import { BatchSummary, PreviewState } from "../types";
import { ApiBridge } from "../api/bridge";

export function useBatch() {
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [progress, setProgress] = useState<{ current: number; total: number; message: string }>({
    current: 0,
    total: 0,
    message: "Ready to process",
  });
  const [stats, setStats] = useState<{ success: number; failed: number }>({ success: 0, failed: 0 });
  const [batchErrors, setBatchErrors] = useState<string[]>([]);

  useEffect(() => {
    window.__onBatchProgress = (current: number, total: number, message: string) => {
      setProgress({ current, total, message });
    };

    window.__onBatchFinishedSummary = (summary: BatchSummary) => {
      setIsProcessing(false);
      const { success, failed, skipped, cancelled, errors, duration } = summary;
      setProgress({
        current: success + failed + (skipped || 0),
        total: summary.planned || success + failed + (skipped || 0),
        message: cancelled
          ? `Cancelled after ${duration}s. (${success} saved, ${failed} failed, ${skipped || 0} skipped)`
          : failed > 0
          ? `Completed with issues in ${duration}s: ${success} succeeded, ${failed} failed, ${skipped || 0} skipped.`
          : `Completed in ${duration}s! ${success} previews saved (${skipped || 0} skipped).`,
      });
      setStats({ success, failed });
      if (errors && errors.length > 0) {
        setBatchErrors(errors);
      }
    };

    return () => {
      delete window.__onBatchProgress;
      delete window.__onBatchFinishedSummary;
    };
  }, []);

  const startBatch = useCallback(
    async (inputFolder: string, outputFolder: string, totalFiles: number, config: PreviewState) => {
      if (!inputFolder) return;
      setIsProcessing(true);
      setStats({ success: 0, failed: 0 });
      setBatchErrors([]);
      setProgress({ current: 0, total: totalFiles, message: "Starting batch generation…" });

      try {
        const api = await ApiBridge.getApi(3000);
        if (api) {
          await api.start_batch(inputFolder, outputFolder || inputFolder, config);
        }
      } catch (err) {
        setIsProcessing(false);
        setBatchErrors([err instanceof Error ? err.message : "Failed to start batch"]);
      }
    },
    []
  );

  const cancelBatch = useCallback(async () => {
    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        await api.cancel_batch();
      }
    } catch {
      // Ignored
    }
  }, []);

  return { isProcessing, progress, stats, batchErrors, startBatch, cancelBatch };
}
