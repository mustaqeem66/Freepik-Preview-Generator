import { useState, useEffect, useCallback, useRef } from "react";
import { FileInfo, ScanFolderResult, ScanStatus } from "../types";
import { ApiBridge, bridgeEvents } from "../api/bridge";

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
  const activeScanId = useRef<string | null>(null);
  const latestScanSeq = useRef(0);
  const scanTerminal = useRef(false);
  const starting = useRef(false);
  // A tiny folder can finish before start_scan's bridge promise resolves.
  const earlyResults = useRef(new Map<string, ScanFolderResult>());

  const applyResult = useCallback((result: ScanFolderResult) => {
    setIsScanning(false);
    activeScanId.current = null;
    if (result.status === "cancelled") {
      setScanStatus("scan-cancelled");
      return;
    }
    if (result.status === "failed") {
      setScanStatus("idle");
      setScanError(result.error || "Folder scanning failed");
      return;
    }
    const truncated = result.truncated === true || TRUNCATED_STATUSES[result.status ?? ""] === true;
    setScanTruncationReasons(result.truncationReasons ?? []);
    setScanDiscovered(result.discovered ?? result.files.length);
    setFileList(result.files);
    setScanStatus(truncated ? "scan-truncated" : "completed");
  }, []);

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
        scanTerminal.current = true;
        applyResult(result);
      } else if (starting.current) {
        if (earlyResults.current.size >= 16) earlyResults.current.clear();
        earlyResults.current.set(scanId, result);
      }
    });
    return () => {
      generation.current++;
      starting.current = false;
      activeScanId.current = null;
      offProgress();
      offFinished();
    };
  }, [applyResult]);

  const scanFolder = useCallback(async (folderPath: string) => {
    const request = ++generation.current;
    activeScanId.current = null;
    latestScanSeq.current = 0;
    scanTerminal.current = false;
    earlyResults.current.clear();
    starting.current = true;
    setScanError(null);
    setScanTruncationReasons([]);
    setScannedCount(0);
    if (!folderPath.trim()) {
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
      const response = await api.start_scan(folderPath);
      if (request !== generation.current) return;
      if (!response.ok || !response.scanId) throw new Error("The folder scan could not be started.");
      activeScanId.current = response.scanId;
      starting.current = false;
      const early = earlyResults.current.get(response.scanId);
      earlyResults.current.clear();
      if (early) applyResult(early);
    } catch (error) {
      if (request !== generation.current) return;
      starting.current = false;
      setIsScanning(false);
      setScanStatus("idle");
      setScanError(error instanceof Error ? error.message : "Folder scanning failed");
    }
  }, [applyResult]);

  const cancelScan = useCallback(async () => {
    generation.current++;
    activeScanId.current = null;
    starting.current = false;
    earlyResults.current.clear();
    setScanStatus("scan-cancelling");
    try {
      const api = await ApiBridge.getApi(2000);
      if (!api) throw new Error("Backend unavailable. The scan cancellation was not delivered.");
      await api.cancel_scan();
      setScanStatus("scan-cancelled");
    } catch (error) {
      setScanStatus("idle");
      setScanError(error instanceof Error ? error.message : "Could not cancel the scan");
    } finally {
      setIsScanning(false);
    }
  }, []);

  return { fileList, setFileList, isScanning, scanStatus,
    scanTruncated: scanStatus === "scan-truncated", scanTruncationReasons,
    scanDiscovered, scannedCount, scanError, scanFolder, cancelScan };
}
