"""Make vm_configs.domain nullable and add preferred_server_type column.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make domain nullable (was NOT NULL)
    op.alter_column("vm_configs", "domain", existing_type=sa.String(), nullable=True)
    # Add preferred_server_type column
    op.add_column("vm_configs", sa.Column("preferred_server_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("vm_configs", "preferred_server_type")
    op.alter_column("vm_configs", "domain", existing_type=sa.String(), nullable=False)
