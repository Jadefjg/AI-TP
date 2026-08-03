"""full_schema_v05

Revision ID: 8fc22864ffb9
Revises: 20250603_0001
Create Date: 2026-06-03 22:49:24.934433

Autogen partial revision: create only when missing (safe after create_all / retry).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "8fc22864ffb9"
down_revision: Union[str, None] = "20250603_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    # Core tables (projects / prompt_templates / ai_artifacts) must already exist
    # (Docker entrypoint create_all, or prior legacy bootstrap). Skip if present.
    if not _has_table("k6_worker_nodes"):
        op.create_table(
            "k6_worker_nodes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("endpoint", sa.String(length=1024), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("weight", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("last_health", sa.String(length=32), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if not _has_table("prompt_feedbacks") and _has_table("projects") and _has_table("prompt_templates"):
        op.create_table(
            "prompt_feedbacks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("module_type", sa.String(length=64), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("original_text", sa.Text(), nullable=False),
            sa.Column("corrected_text", sa.Text(), nullable=False),
            sa.Column("prompt_template_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("applied", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["prompt_template_id"], ["prompt_templates.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_prompt_feedbacks_module_type"), "prompt_feedbacks", ["module_type"], unique=False)

    if not _has_table("k6_dispatch_jobs") and _has_table("projects") and _has_table("ai_artifacts"):
        op.create_table(
            "k6_dispatch_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("plan_snapshot", sa.JSON(), nullable=True),
            sa.Column("node_results", sa.JSON(), nullable=True),
            sa.Column("master_script_path", sa.String(length=1024), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["artifact_id"], ["ai_artifacts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("security_scan_jobs") and _has_table("projects"):
        op.create_table(
            "security_scan_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=True),
            sa.Column("target_url", sa.String(length=2048), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("findings", sa.JSON(), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["artifact_id"], ["ai_artifacts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    if _has_table("security_scan_jobs"):
        op.drop_table("security_scan_jobs")
    if _has_table("k6_dispatch_jobs"):
        op.drop_table("k6_dispatch_jobs")
    if _has_table("prompt_feedbacks"):
        op.drop_index(op.f("ix_prompt_feedbacks_module_type"), table_name="prompt_feedbacks")
        op.drop_table("prompt_feedbacks")
    if _has_table("k6_worker_nodes"):
        op.drop_table("k6_worker_nodes")
