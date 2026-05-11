"""Add vm_firewall_targets table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_firewall_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vm_name", sa.String(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("hetzner_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("firewall_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("vm_name", "project_id", "firewall_name", name="uq_vm_firewall_target"),
    )
    op.create_index("ix_vm_firewall_targets_vm_name", "vm_firewall_targets", ["vm_name"])


def downgrade() -> None:
    op.drop_index("ix_vm_firewall_targets_vm_name", table_name="vm_firewall_targets")
    op.drop_table("vm_firewall_targets")
