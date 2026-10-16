import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
