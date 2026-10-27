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
    port: 5173,
  },
  // @ts-expect-error vitest config extension
  test: {
    globals: true,
    environment: "jsdom",
  },
});
