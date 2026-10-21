import type { FileInfo, PyWebViewApi } from "./types";

export const SCAN_PAGE_MAX_ITEMS = 128;
// The scanner may emit a final ZIP member while marking the 5000-item cap.
export const SCAN_PAGE_MAX_TOTAL = 5001;
export const SCAN_PAGE_TIMEOUT_MS = 8000;

export class ScanTransferSuperseded extends Error {
  constructor() {
    super("Scan result transfer was superseded.");
  }
}

async function boundedPage<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error("Scan result page timed out.")), SCAN_PAGE_TIMEOUT_MS);
      }),
    ]);
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

function isValidFile(file: unknown): file is FileInfo {
  if (!file || typeof file !== "object") return false;
  const row = file as Partial<FileInfo>;
  return typeof row.name === "string" && typeof row.path === "string" &&
    typeof row.ext === "string" && typeof row.is_3d === "boolean";
}

/** Load the final result using bounded bridge responses, never one huge JS event. */
export async function fetchScanPages(
  api: PyWebViewApi | undefined,
  scanId: string,
  total: number,
  isCurrent: () => boolean,
  onProgress?: (count: number) => void,
): Promise<FileInfo[]> {
  if (!Number.isInteger(total) || total <= 0 || total > SCAN_PAGE_MAX_TOTAL || !scanId) {
    throw new Error("Invalid paged scan result metadata.");
  }
  if (!api?.get_scan_page) {
    throw new Error("Update the desktop backend to retrieve scanned assets.");
  }
  const files: FileInfo[] = [];
  let offset = 0;
  while (offset < total) {
    if (!isCurrent()) throw new ScanTransferSuperseded();
    const response = await boundedPage(api.get_scan_page(scanId, offset, SCAN_PAGE_MAX_ITEMS));
    if (!isCurrent()) throw new ScanTransferSuperseded();
    const page = response?.value;
    if (!response?.ok || !page) {
      throw new Error(response?.error || "Could not retrieve the scan result.");
    }
    if (page.scanId !== scanId || page.offset !== offset || page.total !== total ||
        !Array.isArray(page.files) || page.files.length === 0 ||
        page.files.length > SCAN_PAGE_MAX_ITEMS ||
        page.nextOffset !== offset + page.files.length || page.nextOffset > total ||
        !page.files.every(isValidFile)) {
      throw new Error("Received an invalid scan result page. Rescan the source folder.");
    }
    files.push(...page.files);
    offset = page.nextOffset;
    onProgress?.(offset);
  }
  if (!isCurrent()) throw new ScanTransferSuperseded();
  return files;
}
