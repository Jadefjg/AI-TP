"""Workflow polymorphic outputs and idempotency constraints."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "20260916_0012"
down_revision = "a5c7d09c9075"
branch_labels = None
depends_on = None
def upgrade():
    bind = op.get_bind(); cols = {c["name"] for c in inspect(bind).get_columns("agent_workflow_steps")}
    if "output_type" not in cols: op.add_column("agent_workflow_steps", sa.Column("output_type", sa.String(64)))
    if "output_id" not in cols: op.add_column("agent_workflow_steps", sa.Column("output_id", sa.Integer()))
    idx = {i["name"] for i in inspect(bind).get_indexes("agent_workflow_steps")}
    if "uq_agent_workflow_step_position" not in idx: op.create_index("uq_agent_workflow_step_position", "agent_workflow_steps", ["workflow_id", "position"], unique=True)
    if "uq_agent_workflow_step_ai_job" not in idx: op.create_index("uq_agent_workflow_step_ai_job", "agent_workflow_steps", ["ai_job_id"], unique=True)
def downgrade():
    op.drop_index("uq_agent_workflow_step_ai_job", table_name="agent_workflow_steps")
    op.drop_index("uq_agent_workflow_step_position", table_name="agent_workflow_steps")
    op.drop_column("agent_workflow_steps", "output_id"); op.drop_column("agent_workflow_steps", "output_type")
