"""Add enable_ipv4 and enable_ipv6 to vm_archived_states.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vm_archived_states",
        sa.Column("enable_ipv4", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "vm_archived_states",
        sa.Column("enable_ipv6", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("vm_archived_states", "enable_ipv6")
    op.drop_column("vm_archived_states", "enable_ipv4")
