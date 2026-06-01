import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server proxies /api to the FastAPI backend on :8890.
// Production build outputs to dist/, which FastAPI serves via StaticFiles.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8890",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
