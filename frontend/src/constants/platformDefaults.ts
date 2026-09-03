/** Platform API listen address (not the system under test). */
export const PLATFORM_API_BASE_URL = "http://127.0.0.1:8002";

/** @deprecated Prefer resolveProjectBaseUrl(); kept for platform-self references. */
export const DEFAULT_BASE_URL = PLATFORM_API_BASE_URL;

export const DEFAULT_HEALTH_URL = `${PLATFORM_API_BASE_URL}/system/health`;

/** Vite frontend default (vite.config.ts uses strictPort 5174). */
export const DEFAULT_UI_BASE_URL = "http://127.0.0.1:5174";
