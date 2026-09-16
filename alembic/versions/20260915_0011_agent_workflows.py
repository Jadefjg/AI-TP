"""Add persisted Agent workflow runs and steps."""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa
revision = "20260915_0011"
down_revision = "20260911_0010"
branch_labels = None
depends_on = None
def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_workflow_runs" not in tables:
        op.create_table("agent_workflow_runs", sa.Column("id", sa.Integer, primary_key=True), sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="pending"), sa.Column("current_step", sa.Integer, nullable=False, server_default="0"), sa.Column("detail", sa.JSON), sa.Column("input_payload", sa.JSON), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    if "agent_workflow_steps" not in tables:
        op.create_table("agent_workflow_steps", sa.Column("id", sa.Integer, primary_key=True), sa.Column("workflow_id", sa.Integer, sa.ForeignKey("agent_workflow_runs.id"), nullable=False), sa.Column("agent_key", sa.String(64), nullable=False), sa.Column("step_name", sa.String(128), nullable=False), sa.Column("position", sa.Integer, nullable=False, server_default="0"), sa.Column("status", sa.String(32), nullable=False, server_default="pending"), sa.Column("review_status", sa.String(32), nullable=False, server_default="not_required"), sa.Column("artifact_id", sa.Integer, sa.ForeignKey("ai_artifacts.id")), sa.Column("ai_job_id", sa.Integer, sa.ForeignKey("ai_async_jobs.id")), sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"), sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"), sa.Column("trace", sa.JSON), sa.Column("detail", sa.JSON))
    indexes = {i["name"] for i in inspect(op.get_bind()).get_indexes("agent_workflow_runs")}
    if "ix_agent_workflow_runs_project_id" not in indexes: op.create_index("ix_agent_workflow_runs_project_id", "agent_workflow_runs", ["project_id"])
    indexes = {i["name"] for i in inspect(op.get_bind()).get_indexes("agent_workflow_steps")}
    if "ix_agent_workflow_steps_workflow_id" not in indexes: op.create_index("ix_agent_workflow_steps_workflow_id", "agent_workflow_steps", ["workflow_id"])
def downgrade():
    op.drop_table("agent_workflow_steps"); op.drop_table("agent_workflow_runs")
