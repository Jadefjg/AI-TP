"""Add database fallback lease for distributed scheduler lock.

Revision ID: 20260911_0009
Revises: 20260903_0008
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260911_0009"
down_revision: Union[str, None] = "20260903_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    if "scheduler_leases" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "scheduler_leases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("lease_key", sa.String(128), nullable=False, unique=True),
            sa.Column("owner_token", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_scheduler_leases_expires_at", "scheduler_leases", ["expires_at"])

def downgrade() -> None:
    op.drop_table("scheduler_leases")
