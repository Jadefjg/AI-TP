import type {
  AiArtifact,
  AiTaskResult,
  ApiRegressionSet,
  WorkbenchMessage,
  WorkbenchSession,
} from "../types";
import { downloadBlob, openAuthedHtml, req, reqFormData } from "./client";
import { DEFAULT_BASE_URL } from "../constants/platformDefaults";

export type AiAsyncJob = {
  id: number;
  project_id: number;
  organization_id?: number | null;
  module_type: string;
  status: string;
  request_payload?: Record<string, unknown> | null;
  result_payload?: AiTaskResult | null;
  attempt_count?: number;
  max_attempts?: number;
  cancel_requested?: boolean;
  last_error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function pollAiJob(
  projectId: number,
  jobId: number,
  opts?: { intervalMs?: number; timeoutMs?: number },
): Promise<AiTaskResult> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const timeoutMs = opts?.timeoutMs ?? 600_000;
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const job = await req<AiAsyncJob>(
      `/projects/${projectId}/ai/jobs/${jobId}`,
      undefined,
      { timeoutMs: 30_000 },
    );
    if (job.status === "completed") {
      if (!job.result_payload) {
        throw new Error("AI 任务已完成但无结果");
      }
      return job.result_payload;
    }
    if (job.status === "failed" || job.status === "cancelled") {
      throw new Error(job.last_error || `AI 任务${job.status === "cancelled" ? "已取消" : "失败"}`);
    }
    await sleep(intervalMs);
  }
  throw new Error("等待 AI 任务超时，请稍后在任务列表中查看");
}

async function enqueueAiAndWait(
  projectId: number,
  body: Record<string, unknown>,
): Promise<AiTaskResult> {
  const job = await req<AiAsyncJob>(
    `/projects/${projectId}/ai/jobs`,
    { method: "POST", body: JSON.stringify(body) },
    { timeoutMs: 30_000 },
  );
  return pollAiJob(projectId, job.id);
}

export const aiApi = {
  getLlmStatus: () =>
    req<{ configured: boolean; provider: string; high_precision_model: string; bulk_model: string }>(
      "/ai/llm-status",
    ),
  enqueueAiJob: (projectId: number, body: Record<string, unknown>) =>
    req<AiAsyncJob>(
      `/projects/${projectId}/ai/jobs`,
      { method: "POST", body: JSON.stringify(body) },
      { timeoutMs: 30_000 },
    ),
  getAiJob: (projectId: number, jobId: number) =>
    req<AiAsyncJob>(`/projects/${projectId}/ai/jobs/${jobId}`, undefined, { timeoutMs: 30_000 }),
  listAiJobs: (projectId: number, limit = 20) =>
    req<AiAsyncJob[]>(`/projects/${projectId}/ai/jobs?limit=${limit}`),
  aiRequirementReview: (
    projectId: number,
    requirementText: string,
    meta?: { source_filename?: string | null; source_format?: string | null },
  ) =>
    enqueueAiAndWait(projectId, {
      module_type: "requirement_review",
      requirement_text: requirementText,
      source_filename: meta?.source_filename ?? null,
      source_format: meta?.source_format ?? null,
    }),
  parseRequirementDocument: (projectId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return reqFormData<{ text: string; format: string; filename: string; char_count: number }>(
      `/projects/${projectId}/ai/requirement-reviews/parse-document`,
      form,
    );
  },
  aiRequirementReviewUpload: async (projectId: number, file: File) => {
    const parsed = await aiApi.parseRequirementDocument(projectId, file);
    return enqueueAiAndWait(projectId, {
      module_type: "requirement_review",
      requirement_text: parsed.text,
      source_filename: parsed.filename,
      source_format: parsed.format,
    });
  },
  aiRequirementReviewFromUrl: (projectId: number, url: string) =>
    req<AiTaskResult>(
      `/projects/${projectId}/ai/requirement-review/from-url`,
      {
        method: "POST",
        body: JSON.stringify({ url }),
      },
      { timeoutMs: 120_000 },
    ),
  aiFunctionalCases: (projectId: number, body: { requirement_text: string; openapi_content?: string }) =>
    enqueueAiAndWait(projectId, {
      module_type: "functional_cases",
      requirement_text: body.requirement_text,
      openapi_content: body.openapi_content || "",
    }),
  aiApiAutomation: (
    projectId: number,
    body: { case_info: string; api_info: string; case_id?: number | null },
  ) =>
    enqueueAiAndWait(projectId, {
      module_type: "api_automation",
      case_info: body.case_info,
      api_info: body.api_info,
      case_id: body.case_id ?? null,
    }),
  aiOpenApiSpec: (
    projectId: number,
    body?: {
      notes?: string;
      force_ai?: boolean;
      mode?: "discover" | "url" | "manual";
      openapi_url?: string;
      openapi_content?: string;
    },
  ) =>
    req<AiTaskResult>(
      `/projects/${projectId}/ai/openapi-spec`,
      {
        method: "POST",
        body: JSON.stringify({
          notes: body?.notes || "",
          force_ai: Boolean(body?.force_ai),
          mode: body?.mode || "discover",
          openapi_url: body?.openapi_url || "",
          openapi_content: body?.openapi_content || "",
        }),
      },
      { timeoutMs: 120_000 },
    ),
  aiPerfPlan: (projectId: number, body: { biz_desc: string; api_doc?: string }) =>
    enqueueAiAndWait(projectId, {
      module_type: "perf_plan",
      biz_desc: body.biz_desc,
      api_doc: body.api_doc || "",
    }),
  aiSecurityScan: (projectId: number, apiParams: string) =>
    enqueueAiAndWait(projectId, {
      module_type: "security_scan",
      api_params: apiParams,
    }),
  listAiArtifacts: (projectId: number, moduleType?: string) => {
    const q = moduleType ? `?module_type=${encodeURIComponent(moduleType)}` : "";
    return req<AiArtifact[]>(`/projects/${projectId}/ai/artifacts${q}`);
  },
  executeApiArtifact: (
    projectId: number,
    artifactId: number,
    opts?: { baseUrl?: string; scriptContent?: string },
  ) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ai/artifacts/${artifactId}/execute`, {
      method: "POST",
      body: JSON.stringify({
        base_url: opts?.baseUrl || DEFAULT_BASE_URL,
        script_content: opts?.scriptContent,
      }),
    }),
  updateApiArtifactScript: (
    projectId: number,
    artifactId: number,
    body: { script_content: string; title?: string },
  ) =>
    req<AiArtifact>(`/projects/${projectId}/ai/artifacts/${artifactId}/script`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  analyzeApiFailure: (
    projectId: number,
    artifactId: number,
    body?: { execution_result?: Record<string, unknown>; base_url?: string; rerun?: boolean },
  ) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ai/artifacts/${artifactId}/analyze-failure`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  previewDsl: (projectId: number, scriptContent: string, baseUrl?: string) =>
    req<{ valid: boolean; reason: string; steps: Array<Record<string, unknown>> }>(
      `/projects/${projectId}/api-automation/dsl/preview`,
      {
        method: "POST",
        body: JSON.stringify({ script_content: scriptContent, base_url: baseUrl || DEFAULT_BASE_URL }),
      },
    ),
  executeDslStep: (projectId: number, scriptContent: string, stepIndex: number, baseUrl?: string) =>
    req<Record<string, unknown>>(`/projects/${projectId}/api-automation/dsl/execute-step`, {
      method: "POST",
      body: JSON.stringify({
        script_content: scriptContent,
        step_index: stepIndex,
        base_url: baseUrl || DEFAULT_BASE_URL,
      }),
    }),
  listApiRegressionSets: (projectId: number) =>
    req<ApiRegressionSet[]>(`/projects/${projectId}/api-regression-sets`),
  createApiRegressionSet: (
    projectId: number,
    body: { name: string; case_ids: number[]; description?: string; base_url?: string },
  ) =>
    req<ApiRegressionSet>(`/projects/${projectId}/api-regression-sets`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteApiRegressionSet: (projectId: number, setId: number) =>
    req<{ deleted: boolean }>(`/projects/${projectId}/api-regression-sets/${setId}`, { method: "DELETE" }),
  listRequirementReviews: (projectId: number) =>
    req<
      Array<{
        id: number;
        project_id: number;
        model_name: string;
        created_at: string;
        source_filename?: string | null;
        source_format?: string | null;
        requirement_text?: string;
        result_json: Record<string, unknown>;
      }>
    >(`/projects/${projectId}/ai/requirement-reviews`),
  openRequirementReviewHtml: (projectId: number, reviewId: number) => {
    openAuthedHtml(`/projects/${projectId}/ai/requirement-reviews/${reviewId}/html`);
  },
  diffRequirementReviews: (projectId: number, fromId: number, toId: number) =>
    req<{
      summary: { added: number; removed: number; changed: number };
      added: Array<Record<string, unknown>>;
      removed: Array<Record<string, unknown>>;
      changed: Array<Record<string, unknown>>;
    }>(`/projects/${projectId}/ai/requirement-reviews/diff?from_id=${fromId}&to_id=${toId}`),
  convertReviewToCases: (projectId: number, reviewId: number, sections?: string[]) =>
    req<{ review_id: number; case_ids: number[]; count: number; suite_id?: number | null }>(
      `/projects/${projectId}/ai/requirement-reviews/${reviewId}/convert-to-cases`,
      {
        method: "POST",
        body: JSON.stringify({ sections: sections ?? null }),
      },
    ),
  downloadRequirementReviewPdf: (projectId: number, reviewId: number) =>
    downloadBlob(
      `/projects/${projectId}/ai/requirement-reviews/${reviewId}/pdf`,
      `requirement-review-${reviewId}.pdf`,
    ),
  dispatchSecurityArtifact: (
    projectId: number,
    artifactId: number,
    body: {
      target_url: string;
      method?: string;
      query_params?: Record<string, string>;
      body_params?: Record<string, string>;
      headers?: Record<string, string>;
      engine?: string;
    },
  ) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ai/artifacts/${artifactId}/dispatch-security`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listSecurityScanJobs: (projectId: number) =>
    req<Array<Record<string, unknown>>>(`/projects/${projectId}/ai/security-scan-jobs`),
  openSecurityReportHtml: (projectId: number, jobId: number) => {
    openAuthedHtml(`/projects/${projectId}/ai/security-scan-jobs/${jobId}/report.html`);
  },
  downloadSecurityReportPdf: (projectId: number, jobId: number) =>
    downloadBlob(
      `/projects/${projectId}/ai/security-scan-jobs/${jobId}/report.pdf`,
      `security-scan-${jobId}.pdf`,
    ),
  reviewSecurityFinding: (
    projectId: number,
    jobId: number,
    findingIndex: number,
    body: { status: string; note?: string; feed_prompt?: boolean },
  ) =>
    req<Record<string, unknown>>(
      `/projects/${projectId}/ai/security-scan-jobs/${jobId}/findings/${findingIndex}/review`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  listPerfK6Jobs: (projectId: number) =>
    req<Array<Record<string, unknown>>>(`/projects/${projectId}/perf/k6-jobs`),
  getPerfMonitor: (projectId: number, jobId: number) =>
    req<{
      job_id: number;
      status: string;
      summary_metrics: Record<string, unknown>;
      time_series: Array<{ t_sec: number; rt_ms: number; tps: number; error_rate: number }>;
      execution_segments: Array<Record<string, unknown>>;
      bottleneck_analysis: Record<string, unknown> | null;
    }>(`/projects/${projectId}/perf/k6-jobs/${jobId}/monitor`),
  analyzePerfBottleneck: (projectId: number, jobId: number) =>
    req<Record<string, unknown>>(`/projects/${projectId}/perf/k6-jobs/${jobId}/analyze-bottleneck`, {
      method: "POST",
    }),
  dispatchPerfArtifact: (projectId: number, artifactId: number, baseUrl?: string, distributed = false) =>
    req<Record<string, unknown>>(
      `/projects/${projectId}/ai/artifacts/${artifactId}/dispatch-perf`,
      {
        method: "POST",
        body: JSON.stringify({
          base_url: baseUrl || "http://127.0.0.1:8002",
          distributed,
        }),
      },
      { timeoutMs: 180_000 },
    ),
  previewUiScript: (projectId: number, uiScript: unknown, baseUrl?: string) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ui-automation/preview`, {
      method: "POST",
      body: JSON.stringify({ ui_script: uiScript, base_url: baseUrl || "http://127.0.0.1:5173" }),
    }),
  executeUiStep: (projectId: number, uiScript: unknown, stepIndex: number, baseUrl?: string) =>
    req<Record<string, unknown>>(`/projects/${projectId}/ui-automation/execute-step`, {
      method: "POST",
      body: JSON.stringify({
        ui_script: uiScript,
        step_index: stepIndex,
        base_url: baseUrl || "http://127.0.0.1:5173",
      }),
    }),
  getCaseUiScript: (projectId: number, caseId: number) =>
    req<{ case_id: number; ui_script: unknown; playwright_code?: string }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/script`,
    ),
  updateCaseUiScript: (projectId: number, caseId: number, uiScript: unknown) =>
    req<{ case_id: number; ui_script: unknown }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/script`,
      {
        method: "PUT",
        body: JSON.stringify({ ui_script: uiScript }),
      },
    ),
  generateUiFromCase: (projectId: number, caseId: number) =>
    req<{ case_id: number; ui_script: unknown }>(
      `/projects/${projectId}/ui-automation/cases/${caseId}/generate-from-case`,
      { method: "POST" },
    ),
};

export const workbenchApi = {
  listWorkbenchSessions: (projectId: number) =>
    req<WorkbenchSession[]>(`/projects/${projectId}/workbench/sessions`),
  createWorkbenchSession: (projectId: number, body: { module_type: string; title?: string }) =>
    req<WorkbenchSession>(`/projects/${projectId}/workbench/sessions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listWorkbenchMessages: (projectId: number, sessionId: number) =>
    req<WorkbenchMessage[]>(`/projects/${projectId}/workbench/sessions/${sessionId}/messages`),
  workbenchChat: (
    projectId: number,
    sessionId: number,
    body: { message: string; use_rag?: boolean },
  ) =>
    req<{ user: WorkbenchMessage; assistant: WorkbenchMessage }>(
      `/projects/${projectId}/workbench/sessions/${sessionId}/chat`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  applyWorkbenchSession: (projectId: number, sessionId: number) =>
    req<Record<string, unknown>>(`/projects/${projectId}/workbench/sessions/${sessionId}/apply`, {
      method: "POST",
    }),
};

export const integrationsApi = {
  getCiConfig: (projectId: number) => req<import("../types").CiWebhookConfig>(`/projects/${projectId}/integrations/ci`),
  updateCiConfig: (projectId: number, body: Record<string, unknown>) =>
    req<import("../types").CiWebhookConfig>(`/projects/${projectId}/integrations/ci`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  listCiDeliveries: (projectId: number) =>
    req<Array<Record<string, unknown>>>(`/projects/${projectId}/integrations/ci/deliveries`),
};
