from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ProjectCreate(BaseModel):
    organization_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    code_root: str = Field(min_length=1, max_length=1024)
    repo_source: str = Field(default="local", min_length=1, max_length=32)
    repo_branch: str | None = Field(default=None, max_length=255)
    base_url: str | None = Field(default=None, max_length=1024)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    code_root: str = Field(min_length=1, max_length=1024)
    repo_source: str = Field(default="local", min_length=1, max_length=32)
    repo_branch: str | None = Field(default=None, max_length=255)
    base_url: str | None = Field(default=None, max_length=1024)


class ProjectOut(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    code_root: str
    repo_source: str
    repo_branch: str | None
    base_url: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class RecipientCreate(BaseModel):
    email: EmailStr
    display_name: str | None = None


class RecipientOut(BaseModel):
    id: int
    project_id: int
    email: str
    display_name: str | None
    model_config = {"from_attributes": True}


class RequirementIn(BaseModel):
    requirement_text: str = Field(min_length=10)


class KnowledgeIn(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    tags: list[str] | None = None


class KnowledgeChunkOut(BaseModel):
    id: int
    project_id: int
    source: str
    title: str | None
    content: str
    tags: list | None
    embedding_model: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class KnowledgeSearchHit(BaseModel):
    id: int
    source: str
    title: str | None
    content: str
    score: float | None = None
    embedding_model: str | None = None


class KnowledgeSearchOut(BaseModel):
    query: str
    hits: list[KnowledgeSearchHit] = Field(default_factory=list)


class FunctionalCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    module: str | None = Field(default=None, max_length=128)
    preconditions: str | None = None
    steps: list[str] = Field(default_factory=list)
    expected: str | None = None
    priority: str | None = Field(default="medium", max_length=32)
    source_requirement: str | None = None
    openapi_operation_id: str | None = Field(default=None, max_length=255)


class FunctionalCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    module: str | None = Field(default=None, max_length=128)
    preconditions: str | None = None
    steps: list[str] | None = None
    expected: str | None = None
    priority: str | None = Field(default=None, max_length=32)
    source_requirement: str | None = None
    openapi_operation_id: str | None = Field(default=None, max_length=255)
    ui_script: dict | list | None = None


class FunctionalCaseBatchImport(BaseModel):
    cases: list[FunctionalCaseCreate] = Field(min_length=1)


class OpenApiImportIn(BaseModel):
    openapi_content: str = Field(min_length=1, description="OpenAPI/Swagger JSON 或 YAML 全文")
    persist: bool = Field(default=True, description="True=入库, False=仅预览骨架")


class FunctionalCaseOut(BaseModel):
    id: int
    project_id: int
    title: str
    module: str | None = None
    preconditions: str | None
    steps: list
    expected: str | None
    priority: str | None
    source_requirement: str | None
    openapi_operation_id: str | None = None
    ui_script: dict | list | None = None
    created_at: datetime
    updated_at: datetime | None = None
    model_config = {"from_attributes": True}


class TestPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="draft", max_length=32)


class TestPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, max_length=32)


class TestPlanOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class TestSuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    plan_id: int | None = None


class TestSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    plan_id: int | None = None


class TestSuiteOut(BaseModel):
    id: int
    project_id: int
    plan_id: int | None
    name: str
    description: str | None
    created_at: datetime
    case_count: int = 0
    model_config = {"from_attributes": True}


class SuiteAssignCasesIn(BaseModel):
    case_ids: list[int] = Field(default_factory=list)


class AgentGenerateOut(BaseModel):
    cases: list[FunctionalCaseOut]
    contexts: list[dict]


class RunCreate(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    suite_id: int | None = None
    plan_id: int | None = None
    command_overrides: dict[str, str] | None = None
    api_base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)
    api_mode: str = Field(default="auto", description="auto|dsl|pytest")
    regression_set_id: int | None = None
    api_artifact_ids: list[int] | None = None
    perf_base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)
    perf_mode: str = Field(default="auto", description="auto|k6|legacy")
    perf_artifact_id: int | None = None
    perf_distributed: bool | None = None
    security_mode: str = Field(default="auto", description="auto|ai|legacy|combined")
    security_target_url: str = Field(default="http://127.0.0.1:8002/system/health", max_length=2048)
    security_artifact_id: int | None = None
    security_engine: str = Field(default="builtin", description="builtin|nuclei|zap")


class ApiRegressionSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    case_ids: list[int] = Field(min_length=1)
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)


class ApiRegressionSetOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None
    case_ids: list[int]
    base_url: str
    created_at: datetime
    model_config = {"from_attributes": True}


class DslPreviewIn(BaseModel):
    script_content: str = Field(min_length=1)
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)


class DslStepExecuteIn(BaseModel):
    script_content: str = Field(min_length=1)
    step_index: int = Field(ge=0)
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)


class ApiArtifactScriptUpdate(BaseModel):
    script_content: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=255)


class ApiFailureAnalyzeIn(BaseModel):
    execution_result: dict | None = None
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)
    rerun: bool = Field(default=False, description="无 execution_result 时先执行 DSL")


class RunItemOut(BaseModel):
    id: int
    kind: str
    status: str
    command: str | None
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    detail: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    model_config = {"from_attributes": True}


class ExecutionJobOut(BaseModel):
    id: int
    run_id: int
    job_type: str
    status: str
    attempt_count: int
    max_attempts: int
    cancel_requested: bool
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    project_id: int
    status: str
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    items: list[RunItemOut] = []
    execution_job: ExecutionJobOut | None = None
    model_config = {"from_attributes": True}


class RunTaskOut(BaseModel):
    id: int
    project_id: int
    project_name: str | None = None
    status: str
    created_at: datetime
    completed_at: datetime | None
    kinds: list[str] = Field(default_factory=list)
    failed_item_count: int = 0
    skipped_item_count: int = 0
    item_count: int = 0
    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    run_id: int
    format: str
    created_at: datetime
    content_preview: str


class ReportEmailIn(BaseModel):
    """Optional ad-hoc recipients for one-shot send."""

    emails: list[EmailStr] = Field(default_factory=list)
    save_recipients: bool = False


class ReportEmailOut(BaseModel):
    ok: bool
    sent_to: list[str]
    report_id: int
    skipped: bool = False
    reason: str | None = None
    mode: str | None = None
    outbox_path: str | None = None


class DashboardK6SeriesPoint(BaseModel):
    t_sec: float
    rt_ms: float = 0
    tps: float = 0
    error_rate: float = 0


class DashboardK6Snapshot(BaseModel):
    job_id: int
    project_id: int
    project_name: str | None = None
    status: str
    summary_metrics: dict = Field(default_factory=dict)
    time_series: list[DashboardK6SeriesPoint] = Field(default_factory=list)
    time_series_source: str = "unknown"


class DashboardRunTrendPoint(BaseModel):
    date: str
    total: int = 0
    failed: int = 0
    completed: int = 0


class DashboardRunTrendsOut(BaseModel):
    organization_id: int | None = None
    days: int
    points: list[DashboardRunTrendPoint]


class DashboardSummaryOut(BaseModel):
    organization_id: int | None = None
    project_count: int
    case_count: int
    case_generation_count: int
    unit_run_count: int
    functional_run_count: int = 0
    automation_run_count: int
    performance_run_count: int
    security_run_count: int
    total_run_count: int
    latest_run_status: str | None
    ai_call_count: int = 0
    ai_token_total: int = 0
    failed_run_count: int = 0
    running_run_count: int = 0
    pending_run_count: int = 0
    latest_k6: DashboardK6Snapshot | None = None


class UserCreate(BaseModel):
    organization_id: int | None = None
    role_names: list[str] = Field(default_factory=list)
    username: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserAssignRolesIn(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class UserAdminUpdate(BaseModel):
    organization_id: int | None = None
    is_active: bool | None = None
    role_ids: list[int] | None = None


class UserBatchUpdateFields(BaseModel):
    organization_id: int | None = None
    is_active: bool | None = None
    role_ids: list[int] | None = None


class UserBatchUpdateIn(BaseModel):
    user_ids: list[int] = Field(min_length=1)
    updates: UserBatchUpdateFields


class PermissionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    description: str | None = None


class PermissionOut(BaseModel):
    id: int
    code: str
    description: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None


class RoleAssignPermissionsIn(BaseModel):
    permission_ids: list[int] = Field(default_factory=list)


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    permissions: list[PermissionOut] = []
    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class ChangePasswordIn(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=128)
    encrypted_payload: str = Field(min_length=16, max_length=4096)


class UserOut(BaseModel):
    id: int
    organization_id: int | None = None
    username: str
    display_name: str | None
    email: EmailStr | None
    is_active: bool
    created_at: datetime
    roles: list[RoleOut] = []
    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    max_projects: int = Field(default=100, ge=0)
    monthly_ai_token_quota: int = Field(default=500_000, ge=0)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    max_projects: int | None = Field(default=None, ge=0)
    monthly_ai_token_quota: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class OrganizationOut(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None
    max_projects: int
    monthly_ai_token_quota: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizationMemberIn(BaseModel):
    user_id: int
    role_ids: list[int] = Field(default_factory=list)


class OrganizationMemberByRoleIn(BaseModel):
    user_id: int
    role_names: list[str] = Field(default_factory=list)


class OrganizationMemberOut(BaseModel):
    id: int
    organization_id: int
    user_id: int
    username: str
    display_name: str | None = None
    email: EmailStr | None = None
    is_active: bool = True
    role_names: list[str] = Field(default_factory=list)
    created_at: datetime


class BillingInvoiceOut(BaseModel):
    id: int
    organization_id: int
    period: str
    token_usage: int
    amount_cents: int
    currency: str
    status: str
    stripe_invoice_id: str | None = None
    stripe_checkout_session_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class BillingCheckoutIn(BaseModel):
    invoice_id: int
    success_url: str | None = None
    cancel_url: str | None = None


class BillingCheckoutOut(BaseModel):
    checkout_url: str
    session_id: str
    mock: bool = False


class OrganizationQuotaOut(BaseModel):
    organization_id: int
    slug: str
    project_count: int
    max_projects: int
    monthly_ai_token_quota: int
    monthly_tokens_used: int
    monthly_tokens_remaining: int | None = None


class ProjectAiCredentialIn(BaseModel):
    provider: str = Field(default="openai", max_length=32)
    api_base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=512)
    model_override: str | None = Field(default=None, max_length=128)
    enabled: bool = True


class ProjectAiCredentialOut(BaseModel):
    project_id: int
    configured: bool
    enabled: bool
    provider: str | None = None
    api_base_url: str | None = None
    model_override: str | None = None
    api_key_masked: str | None = None
    updated_at: str | None = None


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None = None
    organization_id: int | None = None
    project_id: int | None = None
    module: str
    action: str
    level: str
    message: str
    detail: dict | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AuditRetentionOut(BaseModel):
    deleted: int


class SystemSettingCreate(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: str
    description: str | None = None


class SystemSettingOut(BaseModel):
    id: int
    key: str
    value: str
    description: str | None
    updated_at: datetime
    model_config = {"from_attributes": True}


class SystemOverviewOut(BaseModel):
    api_name: str
    api_version: str
    project_count: int
    user_count: int
    role_count: int
    permission_count: int
    setting_count: int
    log_count: int


class LoginChallengeOut(BaseModel):
    challenge_id: str
    public_key: str
    algorithm: str = "RSA-OAEP"
    hash_alg: str = "SHA-256"
    expires_in_sec: int


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    challenge_id: str = Field(min_length=8, max_length=128)
    encrypted_password: str = Field(min_length=16, max_length=4096)


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    challenge_id: str = Field(min_length=8, max_length=128)
    encrypted_password: str = Field(min_length=16, max_length=4096)


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_sec: int
    user: UserOut


class PromptTemplateCreate(BaseModel):
    module_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=10)
    model_profile: str = Field(default="bulk_local", max_length=32)
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, min_length=10)
    model_profile: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    new_version: bool = False


class PromptTemplateOut(BaseModel):
    id: int
    module_type: str
    name: str
    content: str
    model_profile: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RequirementReviewIn(BaseModel):
    requirement_text: str = Field(min_length=10)
    source_filename: str | None = None
    source_format: str | None = None


class RequirementReviewUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class RequirementReviewOut(BaseModel):
    id: int
    project_id: int
    requirement_text: str
    result_json: dict
    model_name: str
    prompt_template_id: int | None
    source_filename: str | None = None
    source_format: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class RequirementDocumentParseOut(BaseModel):
    text: str
    format: str
    filename: str
    char_count: int


class ReviewConvertCasesIn(BaseModel):
    sections: list[str] | None = None


class ReviewConvertCasesOut(BaseModel):
    review_id: int
    case_ids: list[int]
    count: int
    suite_id: int | None = None


class RequirementReviewDiffOut(BaseModel):
    from_review_id: int
    to_review_id: int
    from_created_at: str
    to_created_at: str
    summary: dict[str, int]
    added: list[dict]
    removed: list[dict]
    changed: list[dict]


class FunctionalCasesAiIn(BaseModel):
    requirement_text: str = Field(min_length=10)
    openapi_content: str = Field(default="")


class ApiAutomationAiIn(BaseModel):
    case_info: str = Field(min_length=1)
    api_info: str = Field(min_length=1)
    case_id: int | None = None


class OpenApiSpecAiIn(BaseModel):
    notes: str = Field(default="")
    force_ai: bool = False
    # discover: 扫描仓库/部署地址；url: 拉取指定 OpenAPI；manual: 粘贴正文
    mode: str = Field(default="discover", max_length=32)
    openapi_url: str = Field(default="", max_length=2048)
    openapi_content: str = Field(default="")


class PerfPlanAiIn(BaseModel):
    biz_desc: str = Field(min_length=1)
    api_doc: str = Field(default="")


class SecurityScanAiIn(BaseModel):
    api_params: str = Field(min_length=1)


class LlmStatusOut(BaseModel):
    configured: bool
    provider: str
    high_precision_model: str
    bulk_model: str


class AiTaskOut(BaseModel):
    module_type: str
    model: str
    payload: dict | list
    prompt_template_id: int | None
    persisted_ids: list[int] = Field(default_factory=list)
    contexts: list[dict] | None = None
    used_fallback: bool = False


class AiAsyncJobEnqueueIn(BaseModel):
    module_type: str = Field(min_length=1, max_length=64)
    # Module-specific fields (same shapes as sync AI routes).
    requirement_text: str | None = None
    openapi_content: str | None = None
    case_info: str | None = None
    api_info: str | None = None
    case_id: int | None = None
    biz_desc: str | None = None
    api_doc: str | None = None
    api_params: str | None = None
    source_filename: str | None = None
    source_format: str | None = None
    notes: str | None = None
    force_ai: bool = False
    mode: str | None = None
    openapi_url: str | None = None


class AiAsyncJobOut(BaseModel):
    id: int
    project_id: int
    organization_id: int | None
    module_type: str
    status: str
    request_payload: dict | None = None
    result_payload: dict | None = None
    attempt_count: int = 0
    max_attempts: int = 2
    cancel_requested: bool = False
    last_error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_config = {"from_attributes": True}


class AiArtifactOut(BaseModel):
    id: int
    project_id: int
    module_type: str
    title: str | None
    payload: dict | list
    case_id: int | None
    model_name: str
    prompt_template_id: int | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AiUsageSummaryOut(BaseModel):
    total_calls: int
    success_calls: int
    failed_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    by_module: dict[str, int]
    by_model: dict[str, int]


class DashboardOverviewOut(BaseModel):
    summary: DashboardSummaryOut
    run_trends: DashboardRunTrendsOut
    system_overview: SystemOverviewOut | None = None
    ai_usage: AiUsageSummaryOut | None = None


class DslExecuteIn(BaseModel):
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)
    script_content: str | None = Field(default=None, description="覆盖产物内脚本，用于编辑器调试")


class PerfDispatchIn(BaseModel):
    base_url: str = Field(default="http://127.0.0.1:8002", max_length=1024)
    distributed: bool = False


class SecurityScanExecuteIn(BaseModel):
    target_url: str = Field(min_length=8, max_length=2048)
    method: str = Field(default="GET", max_length=16)
    query_params: dict[str, str] = Field(default_factory=dict)
    body_params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    engine: str = Field(default="builtin", description="builtin|nuclei|zap|combined")


class K6WorkerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=1024)
    mode: str = Field(default="http", max_length=32)
    weight: int = Field(default=100, ge=1, le=1000)
    enabled: bool = True


class K6WorkerUpdate(BaseModel):
    endpoint: str | None = Field(default=None, max_length=1024)
    mode: str | None = Field(default=None, max_length=32)
    weight: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool | None = None


class K6WorkerOut(BaseModel):
    id: int
    name: str
    endpoint: str
    mode: str
    weight: int
    enabled: bool
    last_health: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class K6DispatchJobOut(BaseModel):
    id: int
    project_id: int
    artifact_id: int
    status: str
    node_results: list | None
    master_script_path: str | None
    summary_metrics: dict | None = None
    time_series: list | None = None
    execution_segments: list | None = None
    bottleneck_analysis: dict | None = None
    created_at: datetime
    completed_at: datetime | None
    model_config = {"from_attributes": True}


class PerfMonitorOut(BaseModel):
    job_id: int
    status: str
    summary_metrics: dict = Field(default_factory=dict)
    time_series: list = Field(default_factory=list)
    execution_segments: list = Field(default_factory=list)
    bottleneck_analysis: dict | None = None


class SecurityFindingReviewIn(BaseModel):
    status: str = Field(description="confirmed|false_positive|pending")
    note: str | None = None
    feed_prompt: bool = Field(default=True, description="误报/确认反馈写入 Prompt 闭环")


class SecurityScanJobOut(BaseModel):
    id: int
    project_id: int
    artifact_id: int | None
    run_id: int | None = None
    target_url: str
    engine: str = "builtin"
    status: str
    findings: list | None
    finding_reviews: dict | None = None
    detail: dict | None
    created_at: datetime
    model_config = {"from_attributes": True}


class PromptFeedbackIn(BaseModel):
    module_type: str = Field(min_length=1, max_length=64)
    source_type: str = Field(min_length=1, max_length=64)
    source_id: int | None = None
    original_text: str = Field(min_length=1)
    corrected_text: str = Field(min_length=1)
    prompt_template_id: int | None = None
    note: str | None = None
    project_id: int | None = None


class PromptFeedbackOut(BaseModel):
    id: int
    project_id: int | None
    module_type: str
    source_type: str
    source_id: int | None
    original_text: str
    corrected_text: str
    prompt_template_id: int | None
    note: str | None
    applied: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PromptOptimizationOut(BaseModel):
    module_type: str
    feedback_count: int
    active_template_id: int | None
    active_template_version: int | None
    proposed_append: str
    examples: list[dict]


class WorkbenchSessionCreate(BaseModel):
    module_type: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=255)


class WorkbenchSessionOut(BaseModel):
    id: int
    project_id: int
    organization_id: int | None
    user_id: int | None
    module_type: str
    title: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class WorkbenchMessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    rag_refs: list | None = None
    payload: dict | list | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class WorkbenchChatIn(BaseModel):
    message: str = Field(min_length=1)
    use_rag: bool = True
    variables: dict[str, str] | None = None


class WorkbenchChatOut(BaseModel):
    user: WorkbenchMessageOut
    assistant: WorkbenchMessageOut


class CiWebhookConfigOut(BaseModel):
    project_id: int
    enabled: bool
    provider: str
    default_kinds: list[str]
    default_branch: str | None
    pr_comment_enabled: bool
    github_repo: str | None
    webhook_url_hint: str
    secret_masked: str
    model_config = {"from_attributes": True}


class CiWebhookConfigUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = Field(default=None, max_length=32)
    default_kinds: list[str] | None = None
    default_branch: str | None = Field(default=None, max_length=255)
    pr_comment_enabled: bool | None = None
    github_token: str | None = None
    github_repo: str | None = Field(default=None, max_length=512)
    rotate_secret: bool = False


class UiScriptPreviewIn(BaseModel):
    ui_script: dict | list
    base_url: str = Field(default="http://127.0.0.1:5174", max_length=1024)


class UiScriptStepExecuteIn(BaseModel):
    ui_script: dict | list
    step_index: int = Field(ge=0)
    base_url: str = Field(default="http://127.0.0.1:5174", max_length=1024)


class UiScriptUpdateIn(BaseModel):
    ui_script: dict | list
