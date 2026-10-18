import type { AssetProbe, BatchSummary, PyWebViewApi, ScanFolderResult } from "../types";

export type BridgeEventMap = {
  "scan.progress": { scanId: string; count: number };
  "scan.finished": { scanId: string; result: ScanFolderResult };
  "batch.progress": { current: number; total: number; message: string; seq?: number };
  "batch.finished": BatchSummary;
  "preview.completed": { operationId: string; url: string; previewId: string; width: number; height: number };
  "preview.failed": { operationId: string; error: string; code?: string };
  "probe.completed": { operationId: string; probe: AssetProbe };
  "probe.failed": { operationId: string; error: string; code?: string };
};

export type BridgeEnvelope<K extends BridgeEventName = BridgeEventName> = {
  event: K;
  operationId?: string;
  sequence?: number;
  terminal?: boolean;
  payload: BridgeEventMap[K];
};
export type BridgeEventName = keyof BridgeEventMap;
export type BridgeEventMeta = {
  operationId?: string;
  sequence?: number;
  terminal?: boolean;
};
export type BridgeListener<K extends BridgeEventName> = (
  payload: BridgeEventMap[K],
  meta: BridgeEventMeta
) => void;
type ListenerFn = (payload: unknown, meta: BridgeEventMeta) => void;

export class BridgeEventRegistry {
  private listeners = new Map<BridgeEventName, Set<ListenerFn>>();
  constructor() {
    this.attachGlobalBridgeHooks();
  }

  public attachGlobalBridgeHooks(): void {
    if (typeof window === "undefined") return;

    // Centralized typed envelope entrypoint (Finding: Typed Event Hub). Every
    // Python event flows through this single global; the legacy per-callback
    // globals below are retained only as a fallback transport for older bundles.
    window.__onBridgeEvent = (envelope: unknown) => {
      const env = envelope as BridgeEnvelope;
      if (env && env.event) {
        this.emit(env.event, env.payload, {
          operationId: env.operationId,
          sequence: env.sequence,
          terminal: env.terminal,
        });
      }
    };

    window.__onScanProgress = (scanId: string, count: number) => {
      this.emit("scan.progress", { scanId, count }, { operationId: scanId });
    };
    window.__onScanFinished = (scanId: string, result: ScanFolderResult) => {
      this.emit("scan.finished", { scanId, result }, { operationId: scanId, terminal: true });
    };
    window.__onBatchProgress = (current: number, total: number, message: string) => {
      this.emit("batch.progress", { current, total, message }, {});
    };
    window.__onBatchFinishedSummary = (summary: BatchSummary) => {
      this.emit("batch.finished", summary, { terminal: true });
    };
  }

  subscribe<K extends BridgeEventName>(
    event: K,
    listener: BridgeListener<K>
  ): () => void {
    let set = this.listeners.get(event);
    if (!set) {
      set = new Set<ListenerFn>();
      this.listeners.set(event, set);
    }
    const wrapped: ListenerFn = listener as unknown as ListenerFn;
    set.add(wrapped);
    return () => {
      set?.delete(wrapped);
    };
  }

  emit<K extends BridgeEventName>(
    event: K,
    payload: BridgeEventMap[K],
    meta: BridgeEventMeta = {}
  ): void {
    const set = this.listeners.get(event);
    if (!set) return;
    set.forEach((fn) => {
      try {
        fn(payload, meta);
      } catch (err) {
        console.error(`Bridge event listener for "${event}" failed:`, err);
      }
    });
  }

  clear(): void {
    this.listeners.clear();
  }
}
export const bridgeEvents = new BridgeEventRegistry();
export class ApiBridge {
  private static cachedApi: PyWebViewApi | null = null;

  static async getApi(maxWaitMs: number = 3000): Promise<PyWebViewApi | undefined> {
    if (this.cachedApi) {
      return this.cachedApi;
    }

    const immediateApi = window.pywebview?.api;
    if (immediateApi) {
      this.cachedApi = immediateApi;
      return immediateApi;
    }

    const deadline = Date.now() + maxWaitMs;

    while (Date.now() < deadline) {
      const api = window.pywebview?.api;
      if (api) {
        this.cachedApi = api;
        return api;
      }

      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, 50);
      });
    }
    return undefined;
  }

  static clearCache(): void {
    this.cachedApi = null;
  }
}
