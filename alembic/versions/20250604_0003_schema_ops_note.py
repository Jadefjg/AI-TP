"""Schema ops note — prefer alembic over bootstrap patches.

Revision ID: 20250604_0003
Revises: 20250603_0002
Create Date: 2025-06-04

New environments: ``alembic upgrade head`` + ``SCHEMA_BOOTSTRAP_MODE=alembic``.
Legacy SQLite/MySQL: ``SCHEMA_BOOTSTRAP_MODE=bootstrap`` (maps to legacy create_all + patches).
"""

from typing import Sequence, Union

revision: str = "20250604_0003"
down_revision: Union[str, None] = "20250603_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
