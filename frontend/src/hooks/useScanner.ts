import { useState, useEffect, useCallback } from "react";
import { FileInfo } from "../types";
import { ApiBridge } from "../api/bridge";

export function useScanner() {
  const [fileList, setFileList] = useState<FileInfo[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scannedCount, setScannedCount] = useState<number>(0);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => {
    window.__onScanProgress = (_scanId: string, count: number) => {
      setScannedCount(count);
    };

    window.__onScanFinished = (
      _scanId: string,
      result: { files: FileInfo[]; total: number }
    ) => {
      setIsScanning(false);
      if (result?.files) {
        setFileList(result.files);
      }
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
          await api.start_scan(folderPath);
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
