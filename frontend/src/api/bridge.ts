import { PyWebViewApi } from "../types";

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
