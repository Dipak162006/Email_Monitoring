import path from "path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget =
    process.env.VITE_API_PROXY_TARGET ||
    env.VITE_API_PROXY_TARGET ||
    process.env.BACKEND_URL ||
    env.BACKEND_URL ||
    "http://127.0.0.1:8000";

  const usePolling =
    process.env.VITE_USE_POLLING === "true" ||
    env.VITE_USE_POLLING === "true" ||
    process.env.CHOKIDAR_USEPOLLING === "true" ||
    env.CHOKIDAR_USEPOLLING === "true";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      host: "0.0.0.0",
      watch: {
        usePolling,
        interval: 100,
      },
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

