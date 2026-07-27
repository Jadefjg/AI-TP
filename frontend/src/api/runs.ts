import type { ExecutionJob, ReportEmailResult, Run } from "../types";
import { fetchAuthedText, req } from "./client";

export const runsApi = {
  startRun: (
    projectId: number,
    kinds: string[],
    options?: {
      suite_id?: number | null;
      plan_id?: number | null;
      api_base_url?: string;
      api_mode?: string;
      regression_set_id?: number | null;
      api_artifact_ids?: number[];
      perf_base_url?: string;
      perf_mode?: string;
      perf_artifact_id?: number | null;
      perf_distributed?: boolean;
      security_mode?: string;
      security_target_url?: string;
      security_artifact_id?: number | null;
      security_engine?: string;
    },
  ) =>
    req<Run>(`/projects/${projectId}/runs`, {
      method: "POST",
      body: JSON.stringify({
        kinds,
        suite_id: options?.suite_id ?? null,
        plan_id: options?.plan_id ?? null,
        api_base_url: options?.api_base_url,
        api_mode: options?.api_mode,
        regression_set_id: options?.regression_set_id ?? null,
        api_artifact_ids: options?.api_artifact_ids,
        perf_base_url: options?.perf_base_url,
        perf_mode: options?.perf_mode,
        perf_artifact_id: options?.perf_artifact_id ?? null,
        perf_distributed: options?.perf_distributed,
        security_mode: options?.security_mode,
        security_target_url: options?.security_target_url,
        security_artifact_id: options?.security_artifact_id ?? null,
        security_engine: options?.security_engine,
      }),
    }),
  listProjectRuns: (projectId: number) => req<Run[]>(`/projects/${projectId}/runs`),
  getRun: (runId: number) => req<Run>(`/runs/${runId}`),
  cancelRun: (runId: number) => req<ExecutionJob>(`/runs/${runId}/cancel`, { method: "POST" }),
  retryRun: (runId: number) => req<ExecutionJob>(`/runs/${runId}/retry`, { method: "POST" }),
  listRecentRuns: (limit = 30, opts?: { status?: string; failed_first?: boolean }) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (opts?.status) params.set("status", opts.status);
    if (opts?.failed_first === false) params.set("failed_first", "false");
    return req<Array<Record<string, unknown>>>(`/runs/recent?${params}`);
  },
  createReport: (runId: number) => req(`/runs/${runId}/reports`, { method: "POST" }),
  fetchReportHtml: (runId: number) => fetchAuthedText(`/runs/${runId}/reports/html`),
  mailStatus: () =>
    req<{
      configured: boolean;
      mode: string;
      hint: string;
      host?: string;
      dry_run?: boolean;
    }>("/reports/mail-status"),
  sendReport: (
    runId: number,
    body?: { emails?: string[]; save_recipients?: boolean },
  ) =>
    req<ReportEmailResult>(`/runs/${runId}/reports/send-email`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
};
