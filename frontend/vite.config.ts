/// <reference types="vitest/config" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    // Docker Desktop's Windows-host bind mount (docker-compose.yml mounts
    // ./frontend/src from the Windows filesystem) doesn't reliably propagate inotify
    // events into the Linux container, so Vite's default watcher can silently miss
    // file changes and keep serving a stale transform cache. Polling works
    // regardless of that boundary. Dev-only cost (a bit more CPU); production builds
    // don't run a watcher at all.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
