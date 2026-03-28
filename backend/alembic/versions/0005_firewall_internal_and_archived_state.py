"""Add firewall_internal to projects and vm_archived_states table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hetzner_projects",
        sa.Column("firewall_internal", sa.String(), nullable=False, server_default=""),
    )
    op.create_table(
        "vm_archived_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vm_name", sa.String(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column("server_type", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("public_ip", sa.String(), nullable=True),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vm_archived_states_vm_name", "vm_archived_states", ["vm_name"])


def downgrade() -> None:
    op.drop_index("ix_vm_archived_states_vm_name", table_name="vm_archived_states")
    op.drop_table("vm_archived_states")
    op.drop_column("hetzner_projects", "firewall_internal")
