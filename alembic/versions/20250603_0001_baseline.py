"""baseline schema marker for ai-tp v0.4

Revision ID: 20250603_0001
Revises:
Create Date: 2025-06-03

Existing deployments rely on backend.db.bootstrap.create_all + column patches.
Run `alembic upgrade head` on fresh MySQL installs after setting DATABASE_URL.
"""

from typing import Sequence, Union

revision: str = "20250603_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
