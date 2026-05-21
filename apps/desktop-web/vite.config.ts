import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// Vite config for the Phase 1 parallel desktop SPA shell.
//
// - Outputs to dist/ as a static SPA (no SSR). In Phase 2 these assets will
//   be served by pywebview directly from disk.
// - base: "./" so the bundle works under any local file/http origin pywebview
//   chooses (file://, http://127.0.0.1:..., etc).
// - Dev server is 127.0.0.1 only — this app is never exposed publicly.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2022",
  },
});
