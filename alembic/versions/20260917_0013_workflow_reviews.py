"""Add workflow review history and reviewer identity."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260917_0013"
down_revision = "20260916_0012"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("agent_workflow_steps")}
    if "reviewer_id" not in cols:
        op.add_column("agent_workflow_steps", sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id")))
    tables = set(inspect(bind).get_table_names())
    if "agent_workflow_reviews" not in tables:
        op.create_table("agent_workflow_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("agent_workflow_runs.id"), nullable=False),
            sa.Column("step_id", sa.Integer(), sa.ForeignKey("agent_workflow_steps.id"), nullable=False),
            sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_agent_workflow_reviews_workflow_id", "agent_workflow_reviews", ["workflow_id"])
        op.create_index("ix_agent_workflow_reviews_step_id", "agent_workflow_reviews", ["step_id"])

def downgrade():
    op.drop_table("agent_workflow_reviews")
    op.drop_column("agent_workflow_steps", "reviewer_id")
