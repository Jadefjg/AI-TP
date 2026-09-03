"""Ops tables: setting revisions, dictionaries, scheduled jobs.

Revision ID: 20260903_0008
Revises: 20260716_0007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260903_0008"
down_revision: Union[str, None] = "20260716_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("setting_revisions"):
        op.create_table(
            "setting_revisions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("setting_key", sa.String(length=128), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("change_type", sa.String(length=32), nullable=False, server_default="upsert"),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_setting_revisions_setting_key", "setting_revisions", ["setting_key"])

    if not _has_table("dictionaries"):
        op.create_table(
            "dictionaries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=64), nullable=False, unique=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table("dictionary_items"):
        op.create_table(
            "dictionary_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("dictionary_id", sa.Integer(), sa.ForeignKey("dictionaries.id"), nullable=False),
            sa.Column("item_key", sa.String(length=64), nullable=False),
            sa.Column("item_label", sa.String(length=128), nullable=False),
            sa.Column("item_value", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )
        op.create_index("ix_dictionary_items_dictionary_id", "dictionary_items", ["dictionary_id"])

    if not _has_table("scheduled_jobs"):
        op.create_table(
            "scheduled_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("handler_key", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="3600"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(length=32), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_scheduled_jobs_handler_key", "scheduled_jobs", ["handler_key"])

    if not _has_table("scheduled_job_runs"):
        op.create_table(
            "scheduled_job_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("scheduled_jobs.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("trigger", sa.String(length=32), nullable=False, server_default="schedule"),
        )
        op.create_index("ix_scheduled_job_runs_job_id", "scheduled_job_runs", ["job_id"])


def downgrade() -> None:
    for table in (
        "scheduled_job_runs",
        "scheduled_jobs",
        "dictionary_items",
        "dictionaries",
        "setting_revisions",
    ):
        if _has_table(table):
            op.drop_table(table)
