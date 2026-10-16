export interface FileInfo {
  name: string;
  path: string;
  ext: string;
  is_3d: boolean;
}

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
}

export interface BatchSummary {
  planned: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  cancelled: boolean;
  errors: string[];
  duration: number;
}

export interface ApiResponse<T> {
  ok: boolean;
  value: T;
  error: string | null;
}

export interface RenderPreviewData {
  dataUrl: string;
  width: number;
  height: number;
}

export interface ScanFolderResult {
  files: FileInfo[];
  total: number;
}

export interface PyWebViewApi {
  frontend_ready: () => Promise<ApiResponse<string>>;
  get_initial_state: () => Promise<ApiResponse<Partial<PreviewState>>>;
  browse_input_folder: () => Promise<string>;
  browse_output_folder: () => Promise<string>;
  browse_logo: () => Promise<string>;
  browse_font: () => Promise<string>;
  open_folder: (path: string) => Promise<boolean>;
  scan_folder: (path: string) => Promise<ScanFolderResult>;
  start_scan: (path: string) => Promise<{ ok: boolean; scanId: string }>;
  cancel_scan: () => Promise<void>;
  render_preview: (
    filePath: string,
    config: PreviewState
  ) => Promise<ApiResponse<RenderPreviewData | null>>;
  start_batch: (
    inputFolder: string,
    outputFolder: string,
    config: PreviewState
  ) => Promise<void>;
  cancel_batch: () => Promise<void>;
  save_settings: (settings: PreviewState) => Promise<ApiResponse<boolean>>;
}

declare global {
  interface Window {
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
