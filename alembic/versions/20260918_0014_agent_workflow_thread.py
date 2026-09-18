"""Persist LangGraph checkpoint thread identifiers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260918_0014"
down_revision = "20260917_0013"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("agent_workflow_runs")}
    if "thread_id" not in cols:
        op.add_column("agent_workflow_runs", sa.Column("thread_id", sa.String(128), nullable=True))
        op.create_index("ix_agent_workflow_runs_thread_id", "agent_workflow_runs", ["thread_id"], unique=True)


def downgrade():
    op.drop_index("ix_agent_workflow_runs_thread_id", table_name="agent_workflow_runs")
    op.drop_column("agent_workflow_runs", "thread_id")
