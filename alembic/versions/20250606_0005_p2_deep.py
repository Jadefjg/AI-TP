"""P2 deep: org members, billing invoices, org stripe fields

Revision ID: 20250606_0005
Revises: 20250605_0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20250606_0005"
down_revision: Union[str, None] = "20250605_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "stripe_customer_id" not in _cols("organizations"):
        op.add_column("organizations", sa.Column("stripe_customer_id", sa.String(128), nullable=True))
    if "billing_email" not in _cols("organizations"):
        op.add_column("organizations", sa.Column("billing_email", sa.String(320), nullable=True))

    if not _has_table("organization_members"):
        op.create_table(
            "organization_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_organization_members_org", "organization_members", ["organization_id"])
        op.create_index("ix_organization_members_user", "organization_members", ["user_id"])

    if not _has_table("organization_member_roles"):
        op.create_table(
            "organization_member_roles",
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
        )

    if not _has_table("billing_invoices"):
        op.create_table(
            "billing_invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("period", sa.String(7), nullable=False),
            sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("stripe_invoice_id", sa.String(128), nullable=True),
            sa.Column("stripe_checkout_session_id", sa.String(128), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_billing_invoices_org", "billing_invoices", ["organization_id"])


def downgrade() -> None:
    if _has_table("billing_invoices"):
        op.drop_table("billing_invoices")
    if _has_table("organization_member_roles"):
        op.drop_table("organization_member_roles")
    if _has_table("organization_members"):
        op.drop_table("organization_members")
    for col in ("billing_email", "stripe_customer_id"):
        if col in _cols("organizations"):
            op.drop_column("organizations", col)
