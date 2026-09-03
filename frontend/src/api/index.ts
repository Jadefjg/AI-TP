import { adminApi } from "./admin";
import { aiApi, integrationsApi, workbenchApi } from "./ai";
import { uiAutomationApi } from "./uiAutomation";
import { authApi } from "./auth";
import { casesApi } from "./cases";
import { dashboardApi } from "./dashboard";
import { organizationsApi } from "./organizations";
import { projectsApi } from "./projects";
import { rbacApi } from "./rbac";
import { runsApi } from "./runs";

export { authStore } from "./auth-store";
export { API_BASE_URL, API_DISPLAY_URL, BASE_URL } from "./config";
export { authApi } from "./auth";
export { runsApi } from "./runs";
export { dashboardApi } from "./dashboard";
export { projectsApi } from "./projects";
export { casesApi } from "./cases";
export { rbacApi } from "./rbac";
export { adminApi } from "./admin";
export { opsApi } from "./ops";
export { aiApi, workbenchApi, integrationsApi } from "./ai";
export { uiAutomationApi, previewUiScriptLocally } from "./uiAutomation";
export { organizationsApi } from "./organizations";

/** 聚合 API，保持与历史 `import { api } from "../api"` 兼容。 */
export const api = {
  ...authApi,
  ...dashboardApi,
  ...projectsApi,
  ...casesApi,
  ...runsApi,
  ...rbacApi,
  ...adminApi,
  ...opsApi,
  ...aiApi,
  ...workbenchApi,
  ...integrationsApi,
  ...organizationsApi,
  ...uiAutomationApi,
};

export type Api = typeof api;
