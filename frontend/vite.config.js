import { defineConfig } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";
import process from "node:process";

// The browser only ever talks to this dev server; /api is forwarded to the FastAPI
// container (API_URL is set in docker-compose.yml).
export default defineConfig({
  plugins: [tailwindcss(), react(), babel({ presets: [reactCompilerPreset()] })],
  server: {
    port: 5173,
    // `web` is this container's name inside Docker, used by the browser check (spikes/m1_ui.mjs).
    allowedHosts: ["web"],
    proxy: {
      "/api": { target: process.env.API_URL || "http://localhost:8000", changeOrigin: true },
    },
  },
});
