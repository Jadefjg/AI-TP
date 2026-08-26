import { req } from "./client";

/** UI 自动化（Playwright DSL）专用 API，避免与 workbench/ai 聚合对象混淆。 */
export const uiAutomationApi = {
  preview: (projectId: number, uiScript: unknown, baseUrl = "http://127.0.0.1:5174") =>
    req<{ valid: boolean; steps: Array<Record<string, unknown>>; base_url?: string }>(
      `/projects/${projectId}/ui-automation/preview`,
      {
        method: "POST",
        body: JSON.stringify({ ui_script: uiScript, base_url: baseUrl }),
      },
    ),
    executeStep: (
    projectId: number,
    uiScript: unknown,
    stepIndex: number,
    baseUrl = "http://127.0.0.1:5174",
  ) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ui-automation/execute-step`, {
      method: "POST",
      body: JSON.stringify({
        ui_script: uiScript,
        step_index: stepIndex,
        base_url: baseUrl,
      }),
    }),
  executeAgent: (projectId: number, uiScript: unknown, baseUrl = "http://127.0.0.1:5174") =>
    req<Record<string, unknown>>(`/projects/${projectId}/ui-automation/execute-agent`, {
      method: "POST",
      body: JSON.stringify({ ui_script: uiScript, base_url: baseUrl }),
    }),
  getCaseScript: (projectId: number, caseId: number) =>
    req<{ case_id: number; ui_script: unknown; playwright_code?: string }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/script`,
    ),
  updateCaseScript: (projectId: number, caseId: number, uiScript: unknown) =>
    req<{ case_id: number; ui_script: unknown }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/script`,
      {
        method: "PUT",
        body: JSON.stringify({ ui_script: uiScript }),
      },
    ),
  generateFromCase: (projectId: number, caseId: number) =>
    req<{ case_id: number; ui_script: unknown }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/generate-from-case`,
      { method: "POST" },
    ),
};

/** 纯前端解析，接口不可用时仍可预览步骤结构。 */
export const previewUiScriptLocally = (uiScript: unknown, baseUrl = "http://127.0.0.1:5174") => {
  const doc =
    Array.isArray(uiScript)
      ? { version: "1", base_url: baseUrl, steps: uiScript }
      : uiScript && typeof uiScript === "object"
        ? {
            version: "1",
            steps: [],
            ...(uiScript as Record<string, unknown>),
            base_url: baseUrl,
          }
        : { version: "1", base_url: baseUrl, steps: [] };

  const rawSteps = Array.isArray(doc.steps) ? doc.steps : [];
  const steps = rawSteps
    .map((step, index) => {
      if (!step || typeof step !== "object") return null;
      const row = step as Record<string, unknown>;
      return {
        index,
        name: String(row.name || `step_${index + 1}`),
        action: String(row.action || "goto"),
        selector: row.selector ?? null,
        url: row.url ?? null,
        value: row.value ?? null,
        remark: row.remark ?? null,
      };
    })
    .filter(Boolean);

  return {
    valid: true,
    base_url: String(doc.base_url || baseUrl),
    steps,
    source: "local",
  };
};
