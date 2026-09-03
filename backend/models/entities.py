from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ItemStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    error = "error"


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    max_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    monthly_ai_token_quota: Mapped[int] = mapped_column(Integer, nullable=False, default=500_000)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), default=None)
    billing_email: Mapped[str | None] = mapped_column(String(320), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list[Project]] = relationship(back_populates="organization")
    users: Mapped[list[User]] = relationship(back_populates="organization")
    members: Mapped[list[OrganizationMember]] = relationship(back_populates="organization")
    invoices: Mapped[list[BillingInvoice]] = relationship(back_populates="organization")


organization_member_roles = Table(
    "organization_member_roles",
    Base.metadata,
    Column("organization_id", ForeignKey("organizations.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="organization_memberships")


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="usd")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(128), default=None)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(128), default=None)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    organization: Mapped[Organization] = relationship(back_populates="invoices")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    code_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    repo_source: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    repo_branch: Mapped[str | None] = mapped_column(String(255), default=None)
    # Default SUT / API base URL for AI execute, perf, security (optional).
    base_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="projects")
    recipients: Mapped[list[Recipient]] = relationship(back_populates="project")
    ai_credential: Mapped[ProjectAiCredential | None] = relationship(
        back_populates="project",
        uselist=False,
    )
    cases: Mapped[list[FunctionalCase]] = relationship(back_populates="project")
    runs: Mapped[list[TestRun]] = relationship(back_populates="project")
    knowledge_chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="project")
    workbench_sessions: Mapped[list[AiWorkbenchSession]] = relationship(back_populates="project")
    ci_webhook: Mapped[CiWebhookConfig | None] = relationship(back_populates="project", uselist=False)
    ai_async_jobs: Mapped[list[AiAsyncJob]] = relationship(back_populates="project")


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)

    project: Mapped[Project] = relationship(back_populates="recipients")


test_suite_cases = Table(
    "test_suite_cases",
    Base.metadata,
    Column("suite_id", ForeignKey("test_suites.id"), primary_key=True),
    Column("case_id", ForeignKey("functional_cases.id"), primary_key=True),
    Column("sort_order", Integer, default=0),
)


class FunctionalCase(Base):
    __tablename__ = "functional_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    module: Mapped[str | None] = mapped_column(String(128), default=None)
    preconditions: Mapped[str | None] = mapped_column(Text, default=None)
    steps: Mapped[list] = mapped_column(JSON, nullable=False, insert_default=list)
    expected: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[str | None] = mapped_column(String(32), default="medium")
    source_requirement: Mapped[str | None] = mapped_column(Text, default=None)
    openapi_operation_id: Mapped[str | None] = mapped_column(String(255), default=None)
    ui_script: Mapped[dict | list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="cases")
    suites: Mapped[list[TestSuite]] = relationship(
        secondary=test_suite_cases,
        back_populates="cases",
    )


class TestPlan(Base):
    __tablename__ = "test_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    suites: Mapped[list[TestSuite]] = relationship(back_populates="plan")


class TestSuite(Base):
    __tablename__ = "test_suites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("test_plans.id"), default=None)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped[TestPlan | None] = relationship(back_populates="suites")
    cases: Mapped[list[FunctionalCase]] = relationship(
        secondary=test_suite_cases,
        back_populates="suites",
    )


class ApiRegressionSet(Base):
    __tablename__ = "api_regression_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    case_ids: Mapped[list] = mapped_column(JSON, nullable=False, insert_default=list)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="http://127.0.0.1:8001")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    project: Mapped[Project] = relationship(back_populates="runs")
    items: Mapped[list[TestRunItem]] = relationship(back_populates="run")
    reports: Mapped[list[ReportArtifact]] = relationship(back_populates="run")
    execution_job: Mapped[ExecutionJob | None] = relationship(back_populates="run", uselist=False)


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="test_run")
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.pending.value)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    run: Mapped[TestRun] = relationship(back_populates="execution_job")


class AiAsyncJob(Base):
    """Async AI generation jobs (avoid HTTP timeouts on LLM / agent workflows)."""

    __tablename__ = "ai_async_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.pending.value)
    request_payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    result_payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=2)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    project: Mapped[Project] = relationship(back_populates="ai_async_jobs")


class TestRunItem(Base):
    __tablename__ = "test_run_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ItemStatus.pending.value)
    command: Mapped[str | None] = mapped_column(Text, default=None)
    stdout: Mapped[str | None] = mapped_column(Text, default=None)
    stderr: Mapped[str | None] = mapped_column(Text, default=None)
    exit_code: Mapped[int | None] = mapped_column(default=None)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    run: Mapped[TestRun] = relationship(back_populates="items")


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="html")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[TestRun] = relationship(back_populates="reports")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="manual")
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, default=None)
    embedding: Mapped[list | None] = mapped_column(JSON, default=None)
    embedding_model: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="knowledge_chunks")


class ProjectAiCredential(Base):
    __tablename__ = "project_ai_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    api_base_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    model_override: Mapped[str | None] = mapped_column(String(128), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="ai_credential")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, default=None)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization | None] = relationship(back_populates="users")
    organization_memberships: Mapped[list[OrganizationMember]] = relationship(back_populates="user")
    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles,
        back_populates="users",
    )
    tokens: Mapped[list[AuthToken]] = relationship(back_populates="user")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[User]] = relationship(
        secondary=user_roles,
        back_populates="roles",
    )
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="tokens")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, default=None)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, default=None)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="bulk_local")
    version: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AiCallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, default=None)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), default=None)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    used_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_detail: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementReview(Base):
    __tablename__ = "requirement_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), default=None)
    source_filename: Mapped[str | None] = mapped_column(String(512), default=None)
    source_format: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptFeedback(Base):
    __tablename__ = "prompt_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), default=None)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[int | None] = mapped_column(default=None)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class K6WorkerNode(Base):
    __tablename__ = "k6_worker_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="http")
    weight: Mapped[int] = mapped_column(default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_health: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class K6DispatchJob(Base):
    __tablename__ = "k6_dispatch_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("ai_artifacts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    plan_snapshot: Mapped[dict | None] = mapped_column(JSON, default=None)
    node_results: Mapped[list | None] = mapped_column(JSON, default=None)
    master_script_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    summary_metrics: Mapped[dict | None] = mapped_column(JSON, default=None)
    time_series: Mapped[list | None] = mapped_column(JSON, default=None)
    execution_segments: Mapped[list | None] = mapped_column(JSON, default=None)
    bottleneck_analysis: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class SecurityScanJob(Base):
    __tablename__ = "security_scan_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("ai_artifacts.id"), default=None)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("test_runs.id"), default=None)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="builtin")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    findings: Mapped[list | None] = mapped_column(JSON, default=None)
    finding_reviews: Mapped[dict | None] = mapped_column(JSON, default=None)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiWorkbenchSession(Base):
    __tablename__ = "ai_workbench_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True, default=None)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="workbench_sessions")
    messages: Mapped[list[AiWorkbenchMessage]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AiWorkbenchMessage(Base):
    __tablename__ = "ai_workbench_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("ai_workbench_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rag_refs: Mapped[list | None] = mapped_column(JSON, default=None)
    payload: Mapped[dict | list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[AiWorkbenchSession] = relationship(back_populates="messages")


class CiWebhookConfig(Base):
    __tablename__ = "ci_webhook_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="generic")
    default_kinds: Mapped[list] = mapped_column(JSON, nullable=False, insert_default=list)
    default_branch: Mapped[str | None] = mapped_column(String(255), default="main")
    pr_comment_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    github_token: Mapped[str | None] = mapped_column(Text, default=None)
    github_repo: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="ci_webhook")


class CiWebhookDelivery(Base):
    __tablename__ = "ci_webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    delivery_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("test_runs.id"), default=None)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="generic")
    ref: Mapped[str | None] = mapped_column(String(512), default=None)
    pr_number: Mapped[int | None] = mapped_column(default=None)
    pr_comment_posted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiArtifact(Base):
    __tablename__ = "ai_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    module_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    payload: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("functional_cases.id"), default=None)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SettingRevision(Base):
    """Immutable history for system_settings changes (rollback support)."""

    __tablename__ = "setting_revisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    setting_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upsert")
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dictionary(Base):
    __tablename__ = "dictionaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list[DictionaryItem]] = relationship(back_populates="dictionary", cascade="all, delete-orphan")


class DictionaryItem(Base):
    __tablename__ = "dictionary_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dictionary_id: Mapped[int] = mapped_column(ForeignKey("dictionaries.id"), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    item_label: Mapped[str] = mapped_column(String(128), nullable=False)
    item_value: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    dictionary: Mapped[Dictionary] = relationship(back_populates="items")


class ScheduledJob(Base):
    """Whitelist-only ops jobs (no arbitrary shell/SQL)."""

    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    handler_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    params: Mapped[dict | None] = mapped_column(JSON, default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_status: Mapped[str | None] = mapped_column(String(32), default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    runs: Mapped[list[ScheduledJobRun]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ScheduledJobRun(Base):
    __tablename__ = "scheduled_job_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("scheduled_jobs.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")

    job: Mapped[ScheduledJob] = relationship(back_populates="runs")
