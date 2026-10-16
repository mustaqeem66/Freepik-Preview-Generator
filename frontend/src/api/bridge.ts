import { PyWebViewApi } from "../types";

export class ApiBridge {
  private static cachedApi: PyWebViewApi | null = null;
  private static readinessPromise: Promise<PyWebViewApi | undefined> | null = null;

  static async getApi(maxWaitMs: number = 3000): Promise<PyWebViewApi | undefined> {
    if (this.cachedApi) return this.cachedApi;
    if (window.pywebview?.api) {
      this.cachedApi = window.pywebview.api;
      return this.cachedApi;
    }

    if (!this.readinessPromise) {
      this.readinessPromise = (async () => {
        const start = Date.now();
        while (Date.now() - start < maxWaitMs) {
          if (window.pywebview?.api) {
            this.cachedApi = window.pywebview.api;
            return this.cachedApi;
          }
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, 50);
          });
        }
        return window.pywebview?.api;
      })();
    }

    const api = await this.readinessPromise;
    if (!api) {
      this.readinessPromise = null; // Allow retry on subsequent calls
    }
    return api;
  }
}
