import type { AssetProbe, BatchSummary, PyWebViewApi, ScanFolderResult } from "../types";
import { WebFallbackBridge } from "./webFallbackBridge";

export type BridgeEventMap = {
  "scan.progress": { scanId: string; count: number };
  "scan.finished": { scanId: string; result: ScanFolderResult };
  "batch.progress": { current: number; total: number; message: string; seq?: number };
  "batch.finished": BatchSummary;
  "preview.completed": { operationId: string; url: string; previewId: string; width: number; height: number };
  "preview.failed": { operationId: string; error: string; code?: string };
  "thumbnail.ready": { path: string; url: string };
  "thumbnail.failed": { path: string };
  "comparison.ready": { path: string; url: string };
  "comparison.failed": { path: string };
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

    // Centralized typed envelope entrypoint (Finding: Typed Event Hub). Batch
    // events flow exclusively through this envelope; the globals below remain
    // only for scan events emitted by the scanner bridge.
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
/**
 * True when this document is hosted by a plain browser rather than the
 * desktop runtime.
 *
 * The packaged desktop app loads the bundled frontend over `file:`, so an
 * `http:`/`https:` document is a browser session by definition. The native
 * runtime injects its bridge asynchronously, after the page's own scripts have
 * run, so `window.pywebview` being undefined proves nothing on its own and
 * cannot be used to tell the two apart.
 */
export function isBrowserHostedDocument(protocol: string): boolean {
  return protocol === "http:" || protocol === "https:";
}

export class ApiBridge {
  private static cachedApi: PyWebViewApi | null = null;
  private static browserDemo: WebFallbackBridge | null = null;
  /** Override for the document protocol; used by tests. */
  private static protocolOverride: string | null = null;

  /** Override the detected document protocol. Returns a restore function. */
  static setProtocolOverride(protocol: string | null): () => void {
    const previous = this.protocolOverride;
    this.protocolOverride = protocol;
    return () => {
      this.protocolOverride = previous;
    };
  }

  /** Read the live native bridge without letting a teardown throw. */
  private static _readLiveApi(): PyWebViewApi | undefined {
    try {
      return window.pywebview?.api;
    } catch {
      // The native bridge is being torn down mid-navigation.
      return undefined;
    }
  }

  static async getApi(maxWaitMs: number = 3000): Promise<PyWebViewApi | undefined> {
    // pywebview rebuilds window.pywebview.api whenever the page reloads, so a
    // cached object from the previous document would route calls into a bridge
    // that no longer exists. Trust the live object, fall back to the cache only
    // while the window is mid-navigation.
    //
    // Reading `window.pywebview.api` can itself throw when the native bridge
    // is being torn down mid-navigation, so every access is guarded.
    const liveApi = this._readLiveApi();
    if (liveApi) {
      if (this.cachedApi !== liveApi) this.cachedApi = liveApi;
      return this.cachedApi;
    }
    if (this.cachedApi) {
      return this.cachedApi;
    }
    // Once a browser demo has started, do not wait for a non-existent native
    // bridge on every slider adjustment. A newly injected native API still
    // takes precedence above this branch.
    if (this.browserDemo && !window.pywebview) return this.browserDemo;

    // A plain browser has no native bridge coming, so the handshake window
    // would only delay the demo by its full duration.
    //
    // The protocol override is a test seam and deliberately bypasses the
    // test-mode guard, so the real branch is exercised rather than a
    // parallel code path.
    const protocol = this.protocolOverride ?? window.location.protocol;
    const browserHosted = (this.protocolOverride !== null || import.meta.env.MODE !== "test")
      && isBrowserHostedDocument(protocol);
    if (browserHosted) {
      this.browserDemo ??= new WebFallbackBridge();
      return this.browserDemo;
    }

    const deadline = Date.now() + maxWaitMs;

    while (Date.now() < deadline) {
      const api = this._readLiveApi();
      if (api) {
        this.cachedApi = api;
        return api;
      }

      const { promise, resolve } = Promise.withResolvers<void>();
      window.setTimeout(resolve, 50);
      await promise;
    }
    // The desktop runtime never answered. Never substitute a synthetic bridge
    // for the privileged desktop runtime: a failed native handshake must stay
    // a failure, not silently downgrade to a demo.
    return undefined;
  }

  static clearCache(): void {
    this.cachedApi = null;
    this.browserDemo = null;
  }
}
