import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Everything under /api is forwarded to the Python backend, so the browser
// only ever talks to one origin and CORS stays out of the way in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
