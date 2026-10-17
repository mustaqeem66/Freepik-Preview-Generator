import { useState, useEffect, useCallback, useRef } from "react";
import { FileInfo } from "../types";
import { ApiBridge } from "../api/bridge";

export function useScanner() {
  const [fileList, setFileList] = useState<FileInfo[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scannedCount, setScannedCount] = useState<number>(0);
  const [scanError, setScanError] = useState<string | null>(null);
  const activeScanIdRef = useRef<string | null>(null);

  useEffect(() => {
    window.__onScanProgress = (scanId: string, count: number) => {
      if (scanId !== activeScanIdRef.current) return;
      setScannedCount(count);
    };

    window.__onScanFinished = (
      scanId: string,
      result: { files: FileInfo[]; total: number }
    ) => {
      if (scanId !== activeScanIdRef.current) return;
      setIsScanning(false);
      if (result?.files) {
        setFileList(result.files);
      }
    };

    return () => {
      delete window.__onScanProgress;
      delete window.__onScanFinished;
    };
  }, []);

  const scanFolder = useCallback(async (folderPath: string) => {
    if (!folderPath) return;
    setIsScanning(true);
    setScannedCount(0);
    setScanError(null);

    try {
      const api = await ApiBridge.getApi(3000);
      if (api) {
        if (api.start_scan) {
          const res = await api.start_scan(folderPath);
          activeScanIdRef.current = res.scanId;
        } else {
          const res = await api.scan_folder(folderPath);
          setIsScanning(false);
          if (res?.files) {
            setFileList(res.files);
          }
        }
      }
    } catch (e) {
      setIsScanning(false);
      setScanError(e instanceof Error ? e.message : "Folder scanning failed");
    }
  }, []);

  const cancelScan = useCallback(async () => {
    activeScanIdRef.current = null;
    try {
      const api = await ApiBridge.getApi(2000);
      if (api?.cancel_scan) {
        await api.cancel_scan();
      }
    } finally {
      setIsScanning(false);
    }
  }, []);

  return { fileList, setFileList, isScanning, scannedCount, scanError, scanFolder, cancelScan };
}
