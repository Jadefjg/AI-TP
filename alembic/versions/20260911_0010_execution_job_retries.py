"""Add retry backoff and dead-letter fields to execution jobs."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
revision = "20260911_0010"
down_revision: Union[str, None] = "20260911_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("execution_jobs")}
    for name, col in [("next_retry_at", sa.Column("next_retry_at", sa.DateTime(timezone=True))), ("backoff_seconds", sa.Column("backoff_seconds", sa.Integer(), nullable=False, server_default="30")), ("dead_lettered_at", sa.Column("dead_lettered_at", sa.DateTime(timezone=True)))]:
        if name not in cols: op.add_column("execution_jobs", col)
    op.create_index("ix_execution_jobs_next_retry_at", "execution_jobs", ["next_retry_at"])
def downgrade() -> None:
    for name in ("dead_lettered_at", "backoff_seconds", "next_retry_at"): op.drop_column("execution_jobs", name)
