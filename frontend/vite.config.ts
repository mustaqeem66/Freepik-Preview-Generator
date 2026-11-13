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
    // disabling Vite's DNS-rebinding protection with allowedHosts: true.
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
  },
});
