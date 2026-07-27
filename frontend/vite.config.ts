import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8002";

  return {
    plugins: [vue()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (id.includes("@arco-design/web-vue")) return "arco";
              if (id.includes("echarts") || id.includes("vue-echarts") || id.includes("zrender")) return "echarts";
              if (id.includes("vue-router")) return "vue-router";
              if (id.includes("/vue/")) return "vue";
            }
          },
        },
      },
    },
    server: {
      // 与 mt-edu (5173) 区分；strictPort 避免端口被占用时静默切回 5173
      port: 5174,
      strictPort: true,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
