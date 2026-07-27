"""schema v0.6–v0.8: cases org, execution_jobs, perf/security columns

Revision ID: 20250603_0002
Revises: 8fc22864ffb9
Create Date: 2026-06-03

Fresh installs: alembic upgrade head, then SCHEMA_BOOTSTRAP_MODE=alembic for app seed-only.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20250603_0002"
down_revision: Union[str, None] = "8fc22864ffb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    if not _has_table(table):
        return set()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _column_names(table):
        op.add_column(table, column)


def upgrade() -> None:
    if not _has_table("test_plans"):
        op.create_table(
            "test_plans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("test_suites"):
        op.create_table(
            "test_suites",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["plan_id"], ["test_plans.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("test_suite_cases"):
        op.create_table(
            "test_suite_cases",
            sa.Column("suite_id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["case_id"], ["functional_cases.id"]),
            sa.ForeignKeyConstraint(["suite_id"], ["test_suites.id"]),
            sa.PrimaryKeyConstraint("suite_id", "case_id"),
        )

    if not _has_table("api_regression_sets"):
        op.create_table(
            "api_regression_sets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("case_ids", sa.JSON(), nullable=False),
            sa.Column("base_url", sa.String(length=1024), nullable=False, server_default="http://127.0.0.1:8001"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("execution_jobs"):
        op.create_table(
            "execution_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_type", sa.String(length=32), nullable=False, server_default="test_run"),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["run_id"], ["test_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id"),
        )

    if _has_table("knowledge_chunks"):
        kc_cols = _column_names("knowledge_chunks")
        if "embedding" not in kc_cols:
            _add_column_if_missing("knowledge_chunks", sa.Column("embedding", sa.JSON(), nullable=True))
        if "embedding_model" not in kc_cols:
            _add_column_if_missing(
                "knowledge_chunks",
                sa.Column("embedding_model", sa.String(length=64), nullable=True),
            )

    if _has_table("functional_cases"):
        _add_column_if_missing("functional_cases", sa.Column("module", sa.String(length=128), nullable=True))
        _add_column_if_missing(
            "functional_cases",
            sa.Column("openapi_operation_id", sa.String(length=255), nullable=True),
        )
        _add_column_if_missing(
            "functional_cases",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if _has_table("k6_dispatch_jobs"):
        for col in (
            "summary_metrics",
            "time_series",
            "execution_segments",
            "bottleneck_analysis",
        ):
            _add_column_if_missing("k6_dispatch_jobs", sa.Column(col, sa.JSON(), nullable=True))

    if _has_table("security_scan_jobs"):
        _add_column_if_missing(
            "security_scan_jobs",
            sa.Column("engine", sa.String(length=32), nullable=False, server_default="builtin"),
        )
        _add_column_if_missing("security_scan_jobs", sa.Column("run_id", sa.Integer(), nullable=True))
        _add_column_if_missing("security_scan_jobs", sa.Column("finding_reviews", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_table("execution_jobs"):
        op.drop_table("execution_jobs")
    if _has_table("api_regression_sets"):
        op.drop_table("api_regression_sets")
    if _has_table("test_suite_cases"):
        op.drop_table("test_suite_cases")
    if _has_table("test_suites"):
        op.drop_table("test_suites")
    if _has_table("test_plans"):
        op.drop_table("test_plans")
