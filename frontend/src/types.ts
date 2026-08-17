export type Organization = {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  max_projects: number;
  monthly_ai_token_quota: number;
  is_active: boolean;
  created_at: string;
};

export type OrganizationQuota = {
  organization_id: number;
  slug: string;
  project_count: number;
  max_projects: number;
  monthly_ai_token_quota: number;
  monthly_tokens_used: number;
  monthly_tokens_remaining: number | null;
};

export type OrganizationMember = {
  id: number;
  organization_id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  is_active: boolean;
  role_names: string[];
  created_at: string;
};

export type BillingInvoice = {
  id: number;
  organization_id: number;
  period: string;
  token_usage: number;
  amount_cents: number;
  currency: string;
  status: string;
  stripe_invoice_id: string | null;
  stripe_checkout_session_id: string | null;
  paid_at: string | null;
  created_at: string;
};

export type BillingCheckoutResult = {
  checkout_url: string;
  session_id: string;
  mock?: boolean;
};

export type Project = {
  id: number;
  organization_id?: number;
  name: string;
  description: string | null;
  code_root: string;
  repo_source: string;
  repo_branch: string | null;
  base_url?: string | null;
  created_at: string;
};

export type Recipient = {
  id: number;
  project_id: number;
  email: string;
  display_name: string | null;
};

export type FunctionalCase = {
  id: number;
  project_id: number;
  title: string;
  module?: string | null;
  preconditions: string | null;
  steps: string[];
  expected: string | null;
  priority: string | null;
  source_requirement: string | null;
  openapi_operation_id?: string | null;
  ui_script?: Record<string, unknown> | unknown[] | null;
  created_at: string;
  updated_at?: string | null;
};

export type WorkbenchSession = {
  id: number;
  project_id: number;
  module_type: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type WorkbenchMessage = {
  id: number;
  session_id: number;
  role: string;
  content: string;
  rag_refs?: unknown[] | null;
  payload?: unknown;
  created_at: string;
};

export type CiWebhookConfig = {
  project_id: number;
  enabled: boolean;
  provider: string;
  default_kinds: string[];
  default_branch: string | null;
  pr_comment_enabled: boolean;
  github_repo: string | null;
  webhook_url_hint: string;
  secret_masked: string;
};

export type TestPlan = {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
};

export type ApiRegressionSet = {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  case_ids: number[];
  base_url: string;
  created_at: string;
};

export type TestSuite = {
  id: number;
  project_id: number;
  plan_id: number | null;
  name: string;
  description: string | null;
  created_at: string;
  case_count: number;
};

export type AiTaskResult = {
  module_type: string;
  model: string;
  payload: Record<string, unknown> | unknown[];
  prompt_template_id: number | null;
  persisted_ids: number[];
  contexts?: Array<Record<string, unknown>> | null;
  used_fallback?: boolean;
};

export type PromptTemplate = {
  id: number;
  module_type: string;
  name: string;
  content: string;
  model_profile: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AiUsageSummary = {
  total_calls: number;
  success_calls: number;
  failed_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  by_module: Record<string, number>;
  by_model: Record<string, number>;
};

export type AiArtifact = {
  id: number;
  project_id: number;
  module_type: string;
  title: string | null;
  payload: Record<string, unknown> | unknown[];
  case_id: number | null;
  model_name: string;
  prompt_template_id: number | null;
  created_at: string;
};

export type KnowledgeChunk = {
  id: number;
  project_id: number;
  source: string;
  title: string | null;
  content: string;
  tags: string[] | null;
  created_at: string;
};

export type RunItem = {
  id: number;
  kind: string;
  status: string;
  command: string | null;
  exit_code: number | null;
  stdout: string | null;
  stderr: string | null;
  detail: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ExecutionJob = {
  id: number;
  run_id: number;
  job_type: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  cancel_requested: boolean;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type Run = {
  id: number;
  project_id: number;
  status: string;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  items: RunItem[];
  execution_job?: ExecutionJob | null;
};

export type ReportEmailResult = {
  ok: boolean;
  sent_to: string[];
  report_id: number;
  skipped?: boolean;
  reason?: string | null;
  mode?: string | null;
  outbox_path?: string | null;
};

export type DashboardRunTrendPoint = {
  date: string;
  total: number;
  failed: number;
  completed: number;
};

export type DashboardRunTrends = {
  organization_id?: number | null;
  days: number;
  points: DashboardRunTrendPoint[];
};

export type DashboardK6Snapshot = {
  job_id: number;
  project_id: number;
  project_name: string | null;
  status: string;
  summary_metrics: Record<string, unknown>;
  time_series: Array<{ t_sec: number; rt_ms: number; tps: number; error_rate: number }>;
  time_series_source: string;
};

export type DashboardSummary = {
  organization_id?: number | null;
  project_count: number;
  case_count: number;
  case_generation_count: number;
  unit_run_count: number;
  functional_run_count?: number;
  automation_run_count: number;
  performance_run_count: number;
  security_run_count: number;
  total_run_count: number;
  latest_run_status: string | null;
  ai_call_count?: number;
  ai_token_total?: number;
  failed_run_count?: number;
  running_run_count?: number;
  pending_run_count?: number;
  latest_k6?: DashboardK6Snapshot | null;
};

export type DashboardOverview = {
  summary: DashboardSummary;
  run_trends: DashboardRunTrends;
  system_overview: SystemOverview | null;
  ai_usage: AiUsageSummary | null;
};

export type Permission = {
  id: number;
  code: string;
  description: string | null;
  created_at: string;
};

export type Role = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  permissions: Permission[];
};

export type User = {
  id: number;
  organization_id?: number | null;
  username: string;
  display_name: string | null;
  email: string | null;
  is_active: boolean;
  created_at: string;
  roles: Role[];
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  expires_in_sec: number;
  user: User;
};

export type SystemSetting = {
  id: number;
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
};

export type AuditLog = {
  id: number;
  module: string;
  action: string;
  level: string;
  message: string;
  detail: Record<string, unknown> | null;
  created_at: string;
};

export type SystemOverview = {
  api_name: string;
  api_version: string;
  project_count: number;
  user_count: number;
  role_count: number;
  permission_count: number;
  setting_count: number;
  log_count: number;
};
