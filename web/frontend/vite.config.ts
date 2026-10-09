/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Same origin in development: the session cookies need no CORS.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    // Monaco (~4 MB) is its own chunk, loaded lazily with the editor.
    chunkSizeWarningLimit: 4500,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});
