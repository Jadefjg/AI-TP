"""P2 ecosystem: workbench, CI webhooks, ui_script

Revision ID: 20250607_0006
Revises: 20250606_0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20250607_0006"
down_revision: Union[str, None] = "20250606_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "ui_script" not in _cols("functional_cases"):
        op.add_column("functional_cases", sa.Column("ui_script", sa.JSON(), nullable=True))

    if not _has_table("ai_workbench_sessions"):
        op.create_table(
            "ai_workbench_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("module_type", sa.String(64), nullable=False),
            sa.Column("title", sa.String(255), nullable=False, server_default="新会话"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ai_workbench_sessions_project", "ai_workbench_sessions", ["project_id"])
        op.create_index("ix_ai_workbench_sessions_org", "ai_workbench_sessions", ["organization_id"])

    if not _has_table("ai_workbench_messages"):
        op.create_table(
            "ai_workbench_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("ai_workbench_sessions.id"), nullable=False),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("rag_refs", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ai_workbench_messages_session", "ai_workbench_messages", ["session_id"])

    if not _has_table("ci_webhook_configs"):
        op.create_table(
            "ci_webhook_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, unique=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("secret", sa.String(128), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False, server_default="generic"),
            sa.Column("default_kinds", sa.JSON(), nullable=False),
            sa.Column("default_branch", sa.String(255), nullable=True),
            sa.Column("pr_comment_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("github_token", sa.Text(), nullable=True),
            sa.Column("github_repo", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table("ci_webhook_deliveries"):
        op.create_table(
            "ci_webhook_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("delivery_key", sa.String(255), nullable=False, unique=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("test_runs.id"), nullable=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default="generic"),
            sa.Column("ref", sa.String(512), nullable=True),
            sa.Column("pr_number", sa.Integer(), nullable=True),
            sa.Column("pr_comment_posted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ci_webhook_deliveries_project", "ci_webhook_deliveries", ["project_id"])


def downgrade() -> None:
    for table in ("ci_webhook_deliveries", "ci_webhook_configs", "ai_workbench_messages", "ai_workbench_sessions"):
        if _has_table(table):
            op.drop_table(table)
    if "ui_script" in _cols("functional_cases"):
        op.drop_column("functional_cases", "ui_script")
