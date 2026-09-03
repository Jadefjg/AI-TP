from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_api: str = ""
    deepseek_model: str = "deepseek-chat"
    ai_high_precision_model: str = "gpt-4o"
    ai_bulk_model: str = "gpt-4o-mini"
    ai_fallback_model: str = "gpt-4o-mini"
    ai_local_base_url: str = ""
    ai_local_model: str = ""
    ai_local_api_key: str = "local"
    redis_url: str = ""
    ai_context_ttl_sec: int = 86400
    k6_worker_token: str = ""
    k6_local_worker_endpoint: str = "http://127.0.0.1:8002"
    k6_distributed_enabled: bool = True
    security_scan_max_payloads: int = 8
    security_scan_delay_ms: int = 50
    # When true, fall back to local stub payloads if all LLM calls fail (demo-friendly).
    ai_stub_on_failure: bool = True
    # Optional Feishu/Lark Open API credentials for wiki/docx URL ingestion
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_open_base_url: str = "https://open.feishu.cn"

    database_url: str = "sqlite:///./data/ai_tp.db"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_from: str = "noreply@example.com"
    # When SMTP_HOST is empty, write HTML to local outbox instead of failing (dev-friendly).
    smtp_dry_run: bool = True
    smtp_outbox_dir: str = "./data/mail_outbox"

    default_test_timeout_sec: int = 600
    backend_cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174"
    )
    rag_top_k: int = 5
    rag_chunk_size: int = 500
    rag_embedding_mode: str = "auto"
    rag_embedding_model: str = "text-embedding-3-small"
    rag_vector_min_score: float = 0.05
    auth_token_ttl_hours: int = 24
    auth_login_challenge_ttl_sec: int = 300
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_display_name: str = "Platform Admin"
    # When true, reset bootstrap admin password on startup if it no longer matches env.
    bootstrap_admin_sync_password: bool = False
    auth_registration_enabled: bool = True
    job_worker_enabled: bool = True
    job_worker_in_api: bool = True
    job_queue_backend: str = "db"
    rq_job_timeout_sec: int = 3600
    rq_failure_ttl_sec: int = 86400
    rq_result_ttl_sec: int = 3600
    celery_queue_name: str = "ai_tp_execution"
    run_failure_alert_enabled: bool = True
    run_failure_alert_channels: str = "generic"
    run_failure_webhook_url: str = ""
    dingtalk_webhook_url: str = ""
    dingtalk_webhook_secret: str = ""
    wecom_webhook_url: str = ""
    metrics_enabled: bool = True
    metrics_auth_enabled: bool = False
    metrics_bearer_token: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "ai-tp-api"
    schema_bootstrap_mode: str = "bootstrap"
    default_organization_slug: str = "default"
    ai_credentials_encryption_key: str = ""
    audit_log_retention_days: int = 90
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://127.0.0.1:8001/auth/oidc/callback"
    oidc_scopes: str = "openid profile email"
    oidc_default_organization_slug: str = "default"
    oidc_organization_claim: str = "org_slug"
    oidc_default_member_roles: str = "member"
    oidc_auto_create_organization: bool = False
    oidc_state_ttl_sec: int = 600
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_per_1k_tokens_cents: int = 20
    billing_currency: str = "usd"
    billing_checkout_success_url: str = "http://127.0.0.1:5174/billing/success"
    billing_checkout_cancel_url: str = "http://127.0.0.1:5174/billing/cancel"
    ci_webhook_public_base_url: str = "http://127.0.0.1:8001"

    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.backend_cors_origins.split(",") if x.strip()]

    def llm_configured(self) -> bool:
        return bool(
            self.openai_api_key.strip()
            or self.deepseek_api_key.strip()
            or self.ai_local_base_url.strip()
        )

    def resolved_llm_provider(self) -> str:
        if self.openai_api_key.strip():
            return "openai"
        if self.deepseek_api_key.strip():
            return "deepseek"
        if self.ai_local_base_url.strip():
            return "local"
        return "none"

    def resolved_api_key(self) -> str:
        if self.openai_api_key.strip():
            return self.openai_api_key.strip()
        if self.deepseek_api_key.strip():
            return self.deepseek_api_key.strip()
        if self.ai_local_base_url.strip():
            return self.ai_local_api_key.strip() or "local"
        return ""

    def resolved_base_url(self) -> str:
        if self.openai_api_key.strip():
            return self.openai_base_url.rstrip("/")
        if self.deepseek_api_key.strip():
            base = (
                self.deepseek_base_url.strip()
                or self.deepseek_api.strip()
                or "https://api.deepseek.com"
            ).rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            return base
        if self.ai_local_base_url.strip():
            return self.ai_local_base_url.rstrip("/")
        return self.openai_base_url.rstrip("/")

    def resolved_model_name(self, model: str, *, profile: str = "") -> str:
        candidate = (model or "").strip()
        provider = self.resolved_llm_provider()
        if provider == "deepseek":
            openai_defaults = {"gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"}
            if not candidate or candidate in openai_defaults:
                return self.deepseek_model.strip() or "deepseek-chat"
        if provider == "local" and profile == "bulk":
            local_model = self.ai_local_model.strip()
            if local_model:
                return local_model
        return candidate or self.openai_model

    def resolved_high_precision_model(self) -> str:
        return self.resolved_model_name(self.ai_high_precision_model.strip() or self.openai_model, profile="high")

    def resolved_bulk_model(self) -> str:
        return self.resolved_model_name(self.ai_bulk_model.strip() or self.openai_model, profile="bulk")

    def resolved_fallback_model(self) -> str:
        return self.resolved_model_name(self.ai_fallback_model.strip() or self.openai_model, profile="bulk")


@lru_cache
def get_settings() -> Settings:
    return Settings()
