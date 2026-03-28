"""Add cloudflare_zone_id column to hetzner_projects.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hetzner_projects",
        sa.Column("cloudflare_zone_id", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("hetzner_projects", "cloudflare_zone_id")
