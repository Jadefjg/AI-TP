from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from backend.core.config import get_settings
from backend.db.session import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

from backend.services.auth_service import seed_auth_defaults
from backend.services.tenant_service import seed_default_organization
from backend.services.ai.prompt_service import seed_builtin_templates
from backend.services.engines.k6_scheduler import seed_default_worker

_REQUIRED_TABLES = (
    "organizations",
    "users",
    "projects",
    "test_runs",
    "execution_jobs",
    "functional_cases",
)


def bootstrap_schema() -> None:
    """Apply schema and seed defaults.

    ``schema_bootstrap_mode=alembic``: 仅种子数据（须先 ``alembic upgrade head``）。
    ``schema_bootstrap_mode=legacy`` 或 ``bootstrap``: create_all + 历史 ALTER 补丁（兼容旧环境）。
    """
    settings = get_settings()
    mode = (settings.schema_bootstrap_mode or "legacy").strip().lower()
    if mode == "bootstrap":
        mode = "legacy"

    if mode == "alembic":
        _verify_alembic_schema()
    else:
        Base.metadata.create_all(bind=engine)
        _ensure_legacy_column_patches()
    _seed_defaults()


def _verify_alembic_schema() -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"SCHEMA_BOOTSTRAP_MODE=alembic but tables missing: {missing}. "
            "Run: alembic upgrade head"
        )
    logger.info("alembic schema verified (%d tables present)", len(existing))


def _ensure_legacy_column_patches() -> None:
    """仅 legacy/bootstrap 模式：为旧库补列。新环境请用 Alembic，勿依赖此逻辑。"""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    statements: list[str] = []

    if "projects" in table_names:
        project_columns = {col["name"] for col in inspector.get_columns("projects")}
        if "repo_source" not in project_columns:
            statements.append(
                "ALTER TABLE projects ADD COLUMN repo_source VARCHAR(32) NOT NULL DEFAULT 'local'"
            )
        if "repo_branch" not in project_columns:
            statements.append("ALTER TABLE projects ADD COLUMN repo_branch VARCHAR(255)")

    if "users" in table_names:
        user_columns = {col["name"] for col in inspector.get_columns("users")}
        if "password_hash" not in user_columns:
            statements.append("ALTER TABLE users ADD COLUMN password_hash VARCHAR(512) NOT NULL DEFAULT ''")

    if "functional_cases" in table_names:
        case_columns = {col["name"] for col in inspector.get_columns("functional_cases")}
        if "module" not in case_columns:
            statements.append("ALTER TABLE functional_cases ADD COLUMN module VARCHAR(128)")
        if "openapi_operation_id" not in case_columns:
            statements.append("ALTER TABLE functional_cases ADD COLUMN openapi_operation_id VARCHAR(255)")
        if "updated_at" not in case_columns:
            statements.append("ALTER TABLE functional_cases ADD COLUMN updated_at DATETIME")
        if "ui_script" not in case_columns:
            statements.append("ALTER TABLE functional_cases ADD COLUMN ui_script JSON")

    if "k6_dispatch_jobs" in table_names:
        k6_columns = {col["name"] for col in inspector.get_columns("k6_dispatch_jobs")}
        for col_name, col_type in (
            ("summary_metrics", "JSON"),
            ("time_series", "JSON"),
            ("execution_segments", "JSON"),
            ("bottleneck_analysis", "JSON"),
        ):
            if col_name not in k6_columns:
                statements.append(f"ALTER TABLE k6_dispatch_jobs ADD COLUMN {col_name} {col_type}")

    if "security_scan_jobs" in table_names:
        sec_columns = {col["name"] for col in inspector.get_columns("security_scan_jobs")}
        if "engine" not in sec_columns:
            statements.append("ALTER TABLE security_scan_jobs ADD COLUMN engine VARCHAR(32) NOT NULL DEFAULT 'builtin'")
        if "run_id" not in sec_columns:
            statements.append("ALTER TABLE security_scan_jobs ADD COLUMN run_id INTEGER")
        if "finding_reviews" not in sec_columns:
            statements.append("ALTER TABLE security_scan_jobs ADD COLUMN finding_reviews JSON")

    if "knowledge_chunks" in table_names:
        kc_columns = {col["name"] for col in inspector.get_columns("knowledge_chunks")}
        if "embedding" not in kc_columns:
            statements.append("ALTER TABLE knowledge_chunks ADD COLUMN embedding JSON")
        if "embedding_model" not in kc_columns:
            statements.append("ALTER TABLE knowledge_chunks ADD COLUMN embedding_model VARCHAR(64)")

    if "requirement_reviews" in table_names:
        review_columns = {col["name"] for col in inspector.get_columns("requirement_reviews")}
        if "source_filename" not in review_columns:
            statements.append("ALTER TABLE requirement_reviews ADD COLUMN source_filename VARCHAR(512)")
        if "source_format" not in review_columns:
            statements.append("ALTER TABLE requirement_reviews ADD COLUMN source_format VARCHAR(32)")

    if not statements:
        return

    logger.warning("applying %d legacy ALTER patches — prefer alembic upgrade head for new installs", len(statements))
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                if "duplicate column" in str(exc).lower():
                    logger.debug("skip duplicate patch: %s", stmt)
                    continue
                raise


def _seed_defaults() -> None:
    db = SessionLocal()
    try:
        seed_auth_defaults(db)
        seed_default_organization(db)
        seed_builtin_templates(db)
        seed_default_worker(db)
    finally:
        db.close()
