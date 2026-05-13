"""Add name and email fields to users

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email")
    op.drop_column("users", "name")
