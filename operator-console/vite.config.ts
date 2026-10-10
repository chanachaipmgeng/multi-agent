import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8088,
    proxy: {
      "/api": {
        target: process.env.VITE_GATEWAY_PROXY || "http://127.0.0.1:8700",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": {
        target: process.env.VITE_GATEWAY_PROXY || "http://127.0.0.1:8700",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
