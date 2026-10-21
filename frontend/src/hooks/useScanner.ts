import { useState, useEffect, useCallback, useRef } from "react";
import { FileInfo, PyWebViewApi, ScanFolderResult, ScanStatus } from "../types";
import { ApiBridge, bridgeEvents } from "../api/bridge";
import { fetchScanPages } from "../scannerPages";

export type { ScanStatus };
const TRUNCATED_STATUSES: Record<string, true> = { truncated: true, completed_with_warnings: true };

export function useScanner() {
  const [fileList, setFileList] = useState<FileInfo[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scannedCount, setScannedCount] = useState(0);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<ScanStatus>("idle");
  const [scanTruncationReasons, setScanTruncationReasons] = useState<string[]>([]);
  const [scanDiscovered, setScanDiscovered] = useState(0);
  const generation = useRef(0);
  const activeFolder = useRef("");
  const activeScanId = useRef<string | null>(null);
  const latestScanSeq = useRef(0);
  const scanTerminal = useRef(false);
  const starting = useRef(false);
  // A tiny folder can finish before start_scan's bridge promise resolves.
  const earlyResults = useRef(new Map<string, ScanFolderResult>());
  const lastResultsFolder = useRef("");
  const cancelRequested = useRef(false);
  const cancelDeadline = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearCancelDeadline = useCallback(() => {
    if (cancelDeadline.current !== null) clearTimeout(cancelDeadline.current);
    cancelDeadline.current = null;
  }, []);

  const failCancellation = useCallback((request: number, reason: string) => {
    if (request !== generation.current || !cancelRequested.current || scanTerminal.current) return;
    clearCancelDeadline();
    cancelRequested.current = false;
    activeScanId.current = null;
    starting.current = false;
    setIsScanning(false);
    setScanStatus("idle");
    setScanError(reason);
  }, [clearCancelDeadline]);

  const requestCancelFor = useCallback(async (scanId: string, request: number, knownApi?: PyWebViewApi) => {
    if (request !== generation.current || activeScanId.current !== scanId || scanTerminal.current) return;
    try {
      const api = knownApi ?? await ApiBridge.getApi(2000);
      if (!api) throw new Error("Backend unavailable. Cancellation was not delivered.");
      const result = await api.cancel_scan(scanId);
      if (result && result.ok === false) throw new Error(result.error || "Scan cancellation rejected.");
      // A bridge response only acknowledges the signal. Await scan.finished.
    } catch (error) {
      failCancellation(request, error instanceof Error ? error.message : "Could not cancel the scan.");
    }
  }, [failCancellation]);

  const applyResult = useCallback((result: ScanFolderResult, scanId: string, request: number) => {
    if (request !== generation.current || activeScanId.current !== scanId) return;
    // The scanner has stopped traversing. Suppress subsequent progress events;
    // transfer the completed rows in bounded bridge calls if necessary.
    scanTerminal.current = true;

    const finish = (completed: ScanFolderResult) => {
      if (request !== generation.current || activeScanId.current !== scanId) return;
      clearCancelDeadline();
      cancelRequested.current = false;
      setIsScanning(false);
      activeScanId.current = null;
      if (completed.status === "cancelled") {
        setScanStatus("scan-cancelled");
        return;
      }
      if (completed.status === "failed") {
        setScanStatus("idle");
        setScanError(completed.error || "Folder scanning failed");
        return;
      }
      const truncated = completed.truncated === true ||
        TRUNCATED_STATUSES[completed.status ?? ""] === true;
      setScanTruncationReasons(completed.truncationReasons ?? []);
      setScanDiscovered(completed.discovered ?? completed.files.length);
      setFileList(completed.files);
      lastResultsFolder.current = activeFolder.current;
      setScanStatus(truncated ? "scan-truncated" : "completed");
    };

    if (!result.paged || result.status === "failed" || result.status === "cancelled") {
      finish(result);
      return;
    }
    // No intermediate rows are committed: incomplete transfers must never
    // look like successful (but mysteriously partial) folder scans.
    void (async () => {
      const api = await ApiBridge.getApi(2000);
      const rows = await fetchScanPages(
        api, scanId, result.paged!.total,
        () => request === generation.current && activeScanId.current === scanId,
        (received) => setScannedCount(received),
      );
      finish({ ...result, files: rows });
    })().catch((error: unknown) => {
      if (request !== generation.current || activeScanId.current !== scanId) return;
      clearCancelDeadline();
      cancelRequested.current = false;
      activeScanId.current = null;
      setIsScanning(false);
      setScanStatus("idle");
      setScanError(
        error instanceof Error
          ? `Scan finished, but the results could not be loaded: ${error.message}`
          : "Scan results were incomplete. Rescan this folder.",
      );
    });
  }, [clearCancelDeadline]);

  useEffect(() => {
    const offProgress = bridgeEvents.subscribe("scan.progress", ({ scanId, count }, meta) => {
      if (scanTerminal.current) return;
      if (meta?.sequence && meta.sequence < latestScanSeq.current) return;
      if (meta?.sequence) latestScanSeq.current = meta.sequence;
      if (scanId === activeScanId.current) setScannedCount(count);
    });
    const offFinished = bridgeEvents.subscribe("scan.finished", ({ scanId, result }, meta) => {
      if (meta?.sequence) latestScanSeq.current = Math.max(latestScanSeq.current, meta.sequence);
      if (scanId === activeScanId.current) {
        applyResult(result, scanId, generation.current);
      } else if (starting.current) {
        if (earlyResults.current.size >= 16) earlyResults.current.clear();
        earlyResults.current.set(scanId, result);
      }
    });
    return () => {
      generation.current++;
      starting.current = false;
      activeScanId.current = null;
      cancelRequested.current = false;
      clearCancelDeadline();
      offProgress();
      offFinished();
    };
  }, [applyResult, clearCancelDeadline]);

  const scanFolder = useCallback(async (folderPath: string) => {
    const request = ++generation.current;
    clearCancelDeadline();
    cancelRequested.current = false;
    const selectedFolder = folderPath.trim();
    activeFolder.current = selectedFolder;
    if (selectedFolder !== lastResultsFolder.current) {
      // Old-folder rows must never be displayed as the new folder's assets.
      setFileList([]);
      setScanDiscovered(0);
    }
    activeScanId.current = null;
    latestScanSeq.current = 0;
    scanTerminal.current = false;
    earlyResults.current.clear();
    starting.current = true;
    setScanError(null);
    setScanTruncationReasons([]);
    setScannedCount(0);
    if (!selectedFolder) {
      lastResultsFolder.current = "";
      starting.current = false;
      setFileList([]);
      setIsScanning(false);
      setScanStatus("idle");
      return;
    }
    setIsScanning(true);
    setScanStatus("scanning");
    try {
      const api = await ApiBridge.getApi(3000);
      if (request !== generation.current) return;
      if (!api) throw new Error("Backend unavailable. Reconnect before scanning.");
      // Send the second argument only to bridge builds with the page API.
      // This keeps older pywebview Python method signatures compatible.
      const response = api.get_scan_page
        ? await api.start_scan(selectedFolder, true)
        : await api.start_scan(selectedFolder);
      if (request !== generation.current) {
        // Superseded requests must only cancel their own ID, not a newer scan.
        if (response?.ok && response.scanId) {
          void api.cancel_scan(response.scanId).catch(() => undefined);
        }
        return;
      }
      if (!response.ok || !response.scanId) throw new Error("The folder scan could not be started.");
      activeScanId.current = response.scanId;
      starting.current = false;
      const early = earlyResults.current.get(response.scanId);
      earlyResults.current.clear();
      if (early) applyResult(early, response.scanId, request);
      else if (cancelRequested.current) void requestCancelFor(response.scanId, request, api);
    } catch (error) {
      if (request !== generation.current) return;
      starting.current = false;
      cancelRequested.current = false;
      clearCancelDeadline();
      activeScanId.current = null;
      setIsScanning(false);
      setScanStatus("idle");
      setScanError(error instanceof Error ? error.message : "Folder scanning failed");
    }
  }, [applyResult, clearCancelDeadline, requestCancelFor]);

  const cancelScan = useCallback(async () => {
    if (!isScanning || cancelRequested.current) return;
    if (scanTerminal.current) {
      // The native scan has already ended; cancel only the remaining local
      // page retrieval. The generation gate suppresses late bridge replies.
      generation.current++;
      clearCancelDeadline();
      activeScanId.current = null;
      starting.current = false;
      setIsScanning(false);
      setScanStatus("scan-cancelled");
      return;
    }
    const request = generation.current;
    cancelRequested.current = true;
    setScanStatus("scan-cancelling");
    clearCancelDeadline();
    cancelDeadline.current = setTimeout(() => {
      failCancellation(request, "Cancellation could not be confirmed. Rescan before exporting.");
    }, 30_000);
    const scanId = activeScanId.current;
    if (scanId) await requestCancelFor(scanId, request);
    // If start_scan is still pending, its promise handler sends the ID-scoped
    // cancellation as soon as the backend returns it.
  }, [isScanning, clearCancelDeadline, failCancellation, requestCancelFor]);

  return { fileList, setFileList, isScanning, scanStatus,
    scanTruncated: scanStatus === "scan-truncated", scanTruncationReasons,
    scanDiscovered, scannedCount, scanError, scanFolder, cancelScan };
}
