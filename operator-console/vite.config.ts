import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const gateway = process.env.VITE_GATEWAY_PROXY || "http://127.0.0.1:8700";

/** Match production nginx: only /api/internal/* and /api/healthz reach the gateway. */
const allowlistedProxy = {
  "/api/internal": {
    target: gateway,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
  "/api/healthz": {
    target: gateway,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8088,
    proxy: allowlistedProxy,
  },
  preview: {
    port: 4173,
    proxy: allowlistedProxy,
  },
});
