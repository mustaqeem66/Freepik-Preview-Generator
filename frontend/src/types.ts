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
  desktopNotifications: boolean;
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
  code?: string;
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
  previewSupport?: {
    mode: "raster" | "vector" | "conditional" | "composite" | "font" |
      "mesh" | "cad" | "embedded" | "external_fallback" | "sample" | "container";
    label: string;
    engines: string[];
    caveat: string;
  } | null;
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
  paged?: { total: number; pageSize: number };
  error?: string;
}

export interface PyWebViewApi {
  frontend_ready: () => Promise<ApiResponse<string>>;
  get_window_chrome?: () => Promise<ApiResponse<{ enabled: boolean; platform: "windows" | "linux" | "macos" | "unknown" }>>;
  window_action?: (action: "minimize" | "fullscreen" | "close") =>
    Promise<{ ok: boolean; error: string | null }>;
  get_initial_state: () => Promise<ApiResponse<Partial<PreviewState>>>;
  browse_input_folder: () => Promise<string>;
  browse_files?: () => Promise<ApiResponse<{ files: FileInfo[]; rejected: string[] } | null>>;
  clear_selected_files?: () => Promise<ApiResponse<number>>;
  browse_output_folder: () => Promise<string>;
  browse_logo: () => Promise<string>;
  browse_font: () => Promise<string>;
  open_folder: (
    path: string
  ) => Promise<{ ok: boolean; value: boolean | null; error: string | null; message?: string }>;
  // Delegates to open_folder(), so it can carry the same NO_FOLDER_OPENER message.
  open_diagnostics_folder?: () => Promise<{ ok: boolean; error: string | null; message?: string }>;
  start_scan: (path: string, paged?: boolean) => Promise<{ ok: boolean; scanId?: string; error?: string }>;
  cancel_scan: (scanId?: string) => Promise<{ ok: boolean; cancelled?: boolean; error?: string } | void>;
  get_scan_page?: (scanId: string, offset: number, limit: number) => Promise<ApiResponse<{
    scanId: string; offset: number; total: number; nextOffset: number; files: FileInfo[];
  } | null>>;
  start_preview?: (
    filePath: string,
    config: PreviewState,
    requestId?: number
  ) => Promise<{ ok: boolean; operationId?: string; status?: string; error?: string }>;
  cancel_preview?: (operationId?: string) => Promise<{ ok: boolean }>;
  render_preview: (
    filePath: string,
    config: PreviewState,
    requestId?: number
  ) => Promise<ApiResponse<RenderPreviewData | null>>;
  release_preview: (url: string) => Promise<ApiResponse<boolean>>;
  retain_preview?: (handle: string) => Promise<ApiResponse<boolean>>;
  request_thumbnails?: (paths: string[]) => Promise<ApiResponse<Record<string, string> | null>>;
  request_source_comparison?: (path: string) => Promise<ApiResponse<Record<string, string> | null>>;
  start_probe?: (
    filePath: string,
    requestId?: number
  ) => Promise<{ ok: boolean; operationId?: string; status?: string; error?: string }>;
  cancel_probe?: (operationId?: string) => Promise<{ ok: boolean }>;
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
  ) => Promise<{ ok: boolean; operationId?: string; error?: string }>;
  start_batch_files?: (files: string[], outputFolder: string, config: PreviewState) =>
    Promise<{ ok: boolean; operationId?: string; error?: string }>;
  cancel_batch: () => Promise<{ ok: boolean }>;
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
  }
}
