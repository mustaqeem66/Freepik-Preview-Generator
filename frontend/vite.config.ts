import { defineConfig, type Plugin } from "vite";
import { injectProductionCsp } from "./security/csp.ts";
import react from "@vitejs/plugin-react";

// Keep the native desktop CSP out of Vite dev mode (HMR requires its own
// WebSocket/script privileges); enforce it in shipped dist/index.html instead.
function desktopProductionCsp(): Plugin {
  return {
    name: "previewgen-production-csp",
    apply: "build",
    transformIndexHtml: {
      order: "pre",
      handler: injectProductionCsp,
    },
  };
}

export default defineConfig({
  plugins: [react(), desktopProductionCsp()],
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: false,
    emptyOutDir: true,
  },
  server: {
    // Cloud/browser previews need a reachable interface, not loopback-only.
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
    // Restrict custom proxy hostnames to explicit trusted values rather than
    // disabling Vite's DNS-rebinding protection by allowing every hostname.
    allowedHosts: process.env.PREVIEWGEN_ALLOWED_HOSTS?.split(",")
      .map((host) => host.trim()).filter(Boolean) ?? [],
  },
  preview: {
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
  },
  // @ts-expect-error vitest config extension
  test: {
    globals: true,
    environment: "jsdom",
    // Vitest's default fork pool starts one jsdom environment per test file
    // with unbounded concurrency. On a 4-core runner with limited free memory
    // the pool can fail to start a worker ("Timeout waiting for worker to
    // respond"), which fails the whole suite even though every test passes.
    // Bounding the pool keeps the run deterministic on constrained machines;
    // CI runners still finish it in well under a minute.
    //
    // Vitest 4 removed `poolOptions` in favour of top-level `maxWorkers` /
    // `minWorkers`. The old nested form still worked in Vitest 5 but printed
    // a deprecation warning on every run; the top-level form is the current
    // API and keeps the bound that stops constrained runners from failing to
    // start a worker.
    pool: "forks",
    maxWorkers: 2,
    minWorkers: 1,
  },
});
