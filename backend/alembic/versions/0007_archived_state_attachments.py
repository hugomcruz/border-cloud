"""Add firewalls_json and networks_json to vm_archived_states.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vm_archived_states",
        sa.Column("firewalls_json", sa.String(), nullable=True),
    )
    op.add_column(
        "vm_archived_states",
        sa.Column("networks_json", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vm_archived_states", "networks_json")
    op.drop_column("vm_archived_states", "firewalls_json")
