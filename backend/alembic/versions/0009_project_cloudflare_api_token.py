"""Add cloudflare_api_token to hetzner_projects.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hetzner_projects",
        sa.Column("cloudflare_api_token", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("hetzner_projects", "cloudflare_api_token")
