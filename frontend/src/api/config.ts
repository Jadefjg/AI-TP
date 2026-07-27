/** Dev 默认走 Vite `/api` 代理，避免跨域触发 OPTIONS 预检；生产在 .env 中配置完整后端地址。 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

/** UI 展示用的真实后端地址（开发代理时取 VITE_API_PROXY_TARGET）。 */
export const API_DISPLAY_URL = (() => {
  const publicUrl = (import.meta.env.VITE_API_PUBLIC_URL || "").trim().replace(/\/$/, "");
  if (publicUrl) return publicUrl;
  if (API_BASE_URL.startsWith("http://") || API_BASE_URL.startsWith("https://")) {
    return API_BASE_URL;
  }
  const proxyTarget = (import.meta.env.VITE_API_PROXY_TARGET || "").trim().replace(/\/$/, "");
  return proxyTarget || API_BASE_URL;
})();

export const BASE_URL = API_BASE_URL;
