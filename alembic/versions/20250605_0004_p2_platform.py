"""P2 platform: organizations, quotas, BYOK, audit scope, OIDC-ready schema

Revision ID: 20250605_0004
Revises: 20250604_0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20250605_0004"
down_revision: Union[str, None] = "20250604_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(64), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("max_projects", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("monthly_ai_token_quota", sa.Integer(), nullable=False, server_default="500000"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.execute(
            sa.text(
                "INSERT INTO organizations (slug, name, description, max_projects, monthly_ai_token_quota, is_active) "
                "VALUES ('default', '默认租户', '升级默认组织', 500, 2000000, 1)"
            )
        )

    if "organization_id" not in _cols("projects"):
        op.add_column("projects", sa.Column("organization_id", sa.Integer(), nullable=True))
        op.execute(sa.text("UPDATE projects SET organization_id = (SELECT id FROM organizations WHERE slug='default' LIMIT 1)"))
        op.alter_column("projects", "organization_id", nullable=False)
        op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
        op.create_foreign_key("fk_projects_organization_id", "projects", "organizations", ["organization_id"], ["id"])

    if "organization_id" not in _cols("users"):
        op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
        op.create_index("ix_users_organization_id", "users", ["organization_id"])
        op.create_foreign_key("fk_users_organization_id", "users", "organizations", ["organization_id"], ["id"])

    for table, cols in (
        (
            "audit_logs",
            [
                ("user_id", sa.Integer()),
                ("organization_id", sa.Integer()),
                ("project_id", sa.Integer()),
            ],
        ),
        (
            "ai_call_logs",
            [
                ("organization_id", sa.Integer()),
                ("user_id", sa.Integer()),
            ],
        ),
    ):
        existing = _cols(table)
        for name, col_type in cols:
            if name not in existing:
                op.add_column(table, sa.Column(name, col_type, nullable=True))

    if not _has_table("project_ai_credentials"):
        op.create_table(
            "project_ai_credentials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, unique=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default="openai"),
            sa.Column("api_base_url", sa.String(1024), nullable=True),
            sa.Column("api_key_encrypted", sa.Text(), nullable=True),
            sa.Column("model_override", sa.String(128), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("project_ai_credentials"):
        op.drop_table("project_ai_credentials")
    for table, col in (
        ("ai_call_logs", "user_id"),
        ("ai_call_logs", "organization_id"),
        ("audit_logs", "project_id"),
        ("audit_logs", "organization_id"),
        ("audit_logs", "user_id"),
    ):
        if col in _cols(table):
            op.drop_column(table, col)
    if "organization_id" in _cols("users"):
        op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
        op.drop_index("ix_users_organization_id", table_name="users")
        op.drop_column("users", "organization_id")
    if "organization_id" in _cols("projects"):
        op.drop_constraint("fk_projects_organization_id", "projects", type_="foreignkey")
        op.drop_index("ix_projects_organization_id", table_name="projects")
        op.drop_column("projects", "organization_id")
    if _has_table("organizations"):
        op.drop_table("organizations")
