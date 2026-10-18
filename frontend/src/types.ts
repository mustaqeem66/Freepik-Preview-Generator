export interface FileInfo {
  name: string;
  path: string;
  ext: string;
  is_3d: boolean;
}

/**
 * Stable identity for a discovered asset. Used as the React list key so that
 * virtualization, selection, and filtering never key off array position.
 */
export function assetId(file: FileInfo): string {
  return file.path;
}

export type ScanStatus =
  | "idle"
  | "scanning"
  | "scan-cancelling"
  | "scan-cancelled"
  | "scan-truncated"
  | "cancelled"
  | "completed";
export type BatchStatus =
  | "idle"
  | "generating"
  | "batch-cancelling"
  | "cancelled"
  | "completed"
  | "completed-with-warnings"
  | "completed-with-errors"
  | "failed";

/** Explicit, mutually-exclusive lifecycle states (no overlapping booleans). */
export type LifecycleState =
  | "idle"
  | "scanning"
  | "scan-cancelling"
  | "scan-cancelled"
  | "scan-truncated"
  | "previewing"
  | "generating"
  | "batch-cancelling"
  | "cancelled"
  | "completed"
  | "completed-with-warnings"
  | "completed-with-errors"
  | "failed";

/** Machine-readable truncation reason codes emitted by the backend. */
export type TruncationReason =
  | "maximum_files"
  | "maximum_directories"
  | "maximum_depth"
  | "maximum_time";

export interface PreviewState {
  inputFolder: string;
  outputFolder: string;
  sameFolder: boolean;
  invertTriangles: boolean;
  solidColor: string;
  logoPath: string;
  logoScale: number;
  logoOpacity: number;
  logoPosX: number;
  logoPosY: number;
  text: string;
  textPosX: number;
  textPosY: number;
  textColor: string;
  fontPath: string;
  fontScale: number;
  hasOutline: boolean;
  outlineColor: string;
  outlineThickness: number;
  opacity: number;
  yaw: number;
  pitch: number;
  modelColor?: string;
  theme: "light" | "dark";
  overwritePolicy?: "overwrite" | "skip" | "rename";
  outputWidth: number;
  outputHeight: number;
}

export interface BatchSummary {
  planned: number;
  processed: number;
  remaining: number;
  success: number;
  failed: number;
  skipped: number;
  cancelled: boolean;
  errors: string[];
  duration: number;
  errorCode?: string;
  status?: "completed" | "completed_with_warnings" | "completed_with_errors" | "cancelled" | "failed";
  truncated?: boolean;
  truncationReasons?: TruncationReason[] | string[];
  discovered?: number;
  generationStatus?: string;
}

export interface ApiResponse<T> {
  ok: boolean;
  value: T;
  error: string | null;
}

export interface RenderPreviewData {
  url: string;
  width: number;
  height: number;
  previewId?: string;
}

/** How an asset's resolution may be changed for export. */
export type AssetKind = "vector" | "procedural" | "raster";

export interface AssetProbe {
  kind: AssetKind;
  resizable: boolean;
  nativeWidth: number | null;
  nativeHeight: number | null;
  maxDimension: number;
  defaultDimension: number;
  requestId?: number;
}

export interface ExportResult {
  path: string;
  width: number;
  height: number;
  skipped?: boolean;
}
export interface CalculatedDimensions {
  width: number;
  height: number;
  longest: number;
  aspect: number;
  kind: AssetKind;
  resizable: boolean;
  nativeWidth: number | null;
  nativeHeight: number | null;
  maxDimension: number;
  upscaleCapped: boolean;
}


/** Opaque ownership token for a rendered preview. Release by id, not by URL. */
export interface PreviewHandle {
  id: string;
  url: string;
  requestId: number;
}

export interface ScanFolderResult {
  files: FileInfo[];
  total: number;
  status?: "completed" | "completed_with_warnings" | "cancelled" | "truncated" | "failed";
  truncated?: boolean;
  truncationReasons?: TruncationReason[] | string[];
  discovered?: number;
  error?: string;
}

export interface PyWebViewApi {
  frontend_ready: () => Promise<ApiResponse<string>>;
  get_initial_state: () => Promise<ApiResponse<Partial<PreviewState>>>;
  browse_input_folder: () => Promise<string>;
  browse_output_folder: () => Promise<string>;
  browse_logo: () => Promise<string>;
  browse_font: () => Promise<string>;
  open_folder: (
    path: string
  ) => Promise<{ ok: boolean; value: boolean | null; error: string | null; message?: string }>;
  scan_folder: (path: string) => Promise<ScanFolderResult>;
  start_scan: (path: string) => Promise<{ ok: boolean; scanId: string }>;
  cancel_scan: () => Promise<void>;
  render_preview: (
    filePath: string,
    config: PreviewState,
    requestId?: number
  ) => Promise<ApiResponse<RenderPreviewData | null>>;
  release_preview: (url: string) => Promise<ApiResponse<boolean>>;
  retain_preview?: (handle: string) => Promise<ApiResponse<boolean>>;
  probe_asset?: (filePath: string, requestId?: number) => Promise<ApiResponse<AssetProbe | null>>;
  calculate_export_dimensions?: (
    filePath: string,
    requestedWidth?: number,
    requestedHeight?: number
  ) => Promise<ApiResponse<CalculatedDimensions | null>>;
  export_preview?: (
    filePath: string,
    config: PreviewState
  ) => Promise<ApiResponse<ExportResult | null>>;
  start_batch: (
    inputFolder: string,
    outputFolder: string,
    config: PreviewState
  ) => Promise<void>;
  cancel_batch: () => Promise<void>;
  save_settings: (settings: PreviewState & { revision?: number }) => Promise<ApiResponse<boolean>>;
}

declare global {
  interface Window {
    __onBridgeEvent?: (envelope: unknown) => void;
    pywebview?: {
      api?: PyWebViewApi;
    };
    __onScanProgress?: (scanId: string, count: number) => void;
    __onScanFinished?: (scanId: string, result: ScanFolderResult) => void;
    __onBatchProgress?: (current: number, total: number, message: string) => void;
    __onBatchFinishedSummary?: (summary: BatchSummary) => void;
    __onBatchFinished?: (
      success: number,
      failed: number,
      errors: string[],
      cancelled: boolean
    ) => void;
  }
}
