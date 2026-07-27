import type { AuditLog, PromptTemplate, SystemSetting } from "../types";
import { req } from "./client";

export type SmtpSettings = {
  configured: boolean;
  host: string;
  port: number;
  user: string;
  password_set: boolean;
  use_tls: boolean;
  use_ssl: boolean;
  from_addr: string;
  dry_run: boolean;
  mode: "smtp" | "outbox" | "disabled" | string;
  hint: string;
  warning?: string | null;
};

export const adminApi = {
  listSettings: () => req<SystemSetting[]>("/settings"),
  upsertSetting: (body: { key: string; value: string; description?: string | null }) =>
    req<SystemSetting>("/settings", { method: "POST", body: JSON.stringify(body) }),
  deleteSetting: (key: string) => req<{ ok: boolean; deleted_key: string }>(`/settings/${key}`, { method: "DELETE" }),
  getSmtpSettings: () => req<SmtpSettings>("/settings/smtp"),
  updateSmtpSettings: (body: {
    host?: string;
    port?: number;
    user?: string;
    password?: string;
    use_tls?: boolean;
    use_ssl?: boolean;
    from_addr?: string;
    dry_run?: boolean;
  }) => req<SmtpSettings>("/settings/smtp", { method: "PUT", body: JSON.stringify(body) }),
  listLogs: (module?: string) =>
    req<AuditLog[]>(module ? `/logs?module=${encodeURIComponent(module)}` : "/logs"),
  listAiModules: () => req<string[]>("/ai/modules"),
  listPromptTemplates: (moduleType?: string, activeOnly = false) => {
    const params = new URLSearchParams();
    if (moduleType) params.set("module_type", moduleType);
    if (activeOnly) params.set("active_only", "true");
    const q = params.toString();
    return req<PromptTemplate[]>(`/ai/prompt-templates${q ? `?${q}` : ""}`);
  },
  createPromptTemplate: (body: {
    module_type: string;
    name: string;
    content: string;
    model_profile?: string;
    is_active?: boolean;
  }) => req<PromptTemplate>("/ai/prompt-templates", { method: "POST", body: JSON.stringify(body) }),
  updatePromptTemplate: (
    templateId: number,
    body: { content?: string; new_version?: boolean; is_active?: boolean },
  ) =>
    req<PromptTemplate>(`/ai/prompt-templates/${templateId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deletePromptTemplate: (templateId: number) =>
    req<{ deleted: boolean; template_id: number }>(`/ai/prompt-templates/${templateId}`, {
      method: "DELETE",
    }),
  seedPromptTemplates: () => req<{ ok: boolean }>("/ai/prompt-templates/seed", { method: "POST" }),
  submitPromptFeedback: (body: {
    module_type: string;
    source_type: string;
    source_id?: number | null;
    original_text: string;
    corrected_text: string;
    project_id?: number | null;
    note?: string | null;
  }) => req<{ id: number }>("/ai/prompt-feedback", { method: "POST", body: JSON.stringify(body) }),
  getPromptSuggestions: (moduleType: string) =>
    req<{
      module_type: string;
      feedback_count: number;
      proposed_append: string;
      examples: Array<Record<string, unknown>>;
    }>(`/ai/prompt-feedback/suggestions?module_type=${encodeURIComponent(moduleType)}`),
  applyPromptSuggestions: (moduleType: string) =>
    req<PromptTemplate>(
      `/ai/prompt-templates/apply-suggestions?module_type=${encodeURIComponent(moduleType)}`,
      { method: "POST" },
    ),
  listK6Workers: () => req<Array<Record<string, unknown>>>("/admin/k6-workers"),
  createK6Worker: (body: {
    name: string;
    endpoint: string;
    mode?: string;
    weight?: number;
    enabled?: boolean;
  }) => req<Record<string, unknown>>("/admin/k6-workers", { method: "POST", body: JSON.stringify(body) }),
  healthCheckK6Worker: (workerId: number) =>
    req<Record<string, unknown>>(`/admin/k6-workers/${workerId}/health-check`, { method: "POST" }),
  seedK6Workers: () => req<{ ok: boolean }>("/admin/k6-workers/seed-default", { method: "POST" }),
  listK6DispatchJobs: () => req<Array<Record<string, unknown>>>("/admin/k6-workers/dispatch-jobs"),
};
