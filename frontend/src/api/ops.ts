import { req } from "./client";

export type OpsOverview = {
  api_version: string;
  health_score: number;
  queue: {
    backend: string;
    execution_pending: number;
    execution_running: number;
    ai_pending: number;
    ai_running: number;
  };
  workers: { total: number; enabled: number };
  scheduled_jobs: { total: number; enabled: number };
  settings_count: number;
  audit_count: number;
  alert_channels: Record<string, unknown>;
  recent_alerts: Array<{
    id: number;
    module: string;
    action: string;
    level: string;
    message: string;
    created_at: string | null;
  }>;
};

export type DictionaryItem = {
  id: number;
  dictionary_id: number;
  item_key: string;
  item_label: string;
  item_value: string;
  sort_order: number;
  is_active: boolean;
};

export type Dictionary = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  items: DictionaryItem[];
};

export type ScheduledJob = {
  id: number;
  name: string;
  handler_key: string;
  description: string | null;
  interval_seconds: number;
  enabled: boolean;
  params: Record<string, unknown> | null;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type ScheduledJobRun = {
  id: number;
  job_id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  trigger: string;
};

export type SettingRevision = {
  id: number;
  setting_key: string;
  old_value: string | null;
  new_value: string | null;
  description: string | null;
  change_type: string;
  actor_user_id: number | null;
  created_at: string;
};

export const opsApi = {
  overview: () => req<OpsOverview>("/ops/overview"),
  listDictionaries: (activeOnly = false) =>
    req<Dictionary[]>(`/ops/dictionaries${activeOnly ? "?active_only=true" : ""}`),
  upsertDictionary: (body: { code: string; name: string; description?: string | null; is_active?: boolean }) =>
    req<Dictionary>("/ops/dictionaries", { method: "POST", body: JSON.stringify(body) }),
  upsertDictionaryItem: (
    dictionaryId: number,
    body: { item_key: string; item_label: string; item_value?: string; sort_order?: number; is_active?: boolean },
  ) =>
    req<DictionaryItem>(`/ops/dictionaries/${dictionaryId}/items`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteDictionary: (id: number) => req<{ ok: boolean }>(`/ops/dictionaries/${id}`, { method: "DELETE" }),
  seedDictionaries: () => req<{ ok: boolean }>("/ops/dictionaries/seed", { method: "POST" }),
  listHandlers: () => req<Array<{ key: string; label: string; description: string }>>("/ops/schedule/handlers"),
  listJobs: () => req<ScheduledJob[]>("/ops/schedule/jobs"),
  upsertJob: (body: {
    name: string;
    handler_key: string;
    description?: string | null;
    interval_seconds: number;
    enabled?: boolean;
    params?: Record<string, unknown> | null;
  }) => req<ScheduledJob>("/ops/schedule/jobs", { method: "POST", body: JSON.stringify(body) }),
  enableJob: (jobId: number, enabled: boolean) =>
    req<ScheduledJob>(`/ops/schedule/jobs/${jobId}/enable?enabled=${enabled ? "true" : "false"}`, {
      method: "POST",
    }),
  runJob: (jobId: number) =>
    req<ScheduledJobRun>(`/ops/schedule/jobs/${jobId}/run`, { method: "POST" }),
  listJobRuns: (jobId: number) => req<ScheduledJobRun[]>(`/ops/schedule/jobs/${jobId}/runs`),
  seedJobs: () => req<{ ok: boolean }>("/ops/schedule/seed", { method: "POST" }),
  listSettingRevisions: (key?: string) =>
    req<SettingRevision[]>(key ? `/settings/revisions?key=${encodeURIComponent(key)}` : "/settings/revisions"),
  rollbackSetting: (revisionId: number) =>
    req<{ ok: boolean; setting?: unknown; deleted?: boolean }>(`/settings/revisions/${revisionId}/rollback`, {
      method: "POST",
    }),
};
