"""Add is_superadmin/is_active to users; create hetzner_projects and user_project_permissions tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to users
    op.add_column("users", sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))

    # Create hetzner_projects table
    op.create_table(
        "hetzner_projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("api_token", sa.String(), nullable=False),
        sa.Column("firewall_name", sa.String(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Create user_project_permissions table
    op.create_table(
        "user_project_permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("hetzner_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "project_id"),
    )


def downgrade() -> None:
    op.drop_table("user_project_permissions")
    op.drop_table("hetzner_projects")
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_superadmin")
