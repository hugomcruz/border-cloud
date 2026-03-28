"""Add initiated_by and error_message to operation_logs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operation_logs",
        sa.Column("initiated_by", sa.String(), nullable=False, server_default="system"),
    )
    op.add_column(
        "operation_logs",
        sa.Column("error_message", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operation_logs", "error_message")
    op.drop_column("operation_logs", "initiated_by")
