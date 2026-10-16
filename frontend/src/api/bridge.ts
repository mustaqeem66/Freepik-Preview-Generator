import { PyWebViewApi } from "../types";

export class ApiBridge {
  private static cachedApi: PyWebViewApi | null = null;

  static async getApi(maxWaitMs: number = 3000): Promise<PyWebViewApi | undefined> {
    if (this.cachedApi) return this.cachedApi;
    if (window.pywebview?.api) {
      this.cachedApi = window.pywebview.api;
      return this.cachedApi;
    }
    const start = Date.now();
    while (Date.now() - start < maxWaitMs) {
      if (window.pywebview?.api) {
        this.cachedApi = window.pywebview.api;
        return this.cachedApi;
      }
      const { promise, resolve } = Promise.withResolvers<void>();
      setTimeout(resolve, 50);
      await promise;
    }
    return window.pywebview?.api;
  }
}
