"""Add projects.base_url and ai_async_jobs.

Revision ID: 20260716_0007
Revises: 20250607_0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260716_0007"
down_revision: Union[str, None] = "20250607_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_table("projects") and "base_url" not in _cols("projects"):
        op.add_column("projects", sa.Column("base_url", sa.String(length=1024), nullable=True))

    if not _has_table("ai_async_jobs"):
        op.create_table(
            "ai_async_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("module_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("request_payload", sa.JSON(), nullable=True),
            sa.Column("result_payload", sa.JSON(), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_ai_async_jobs_project_id", "ai_async_jobs", ["project_id"])
        op.create_index("ix_ai_async_jobs_organization_id", "ai_async_jobs", ["organization_id"])
        op.create_index("ix_ai_async_jobs_module_type", "ai_async_jobs", ["module_type"])


def downgrade() -> None:
    if _has_table("ai_async_jobs"):
        op.drop_table("ai_async_jobs")
    if _has_table("projects") and "base_url" in _cols("projects"):
        op.drop_column("projects", "base_url")
