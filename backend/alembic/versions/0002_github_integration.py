"""GitHub integration schema additions for User, Repository, and Branch models

Revision ID: 0002_github_integration
Revises: 0001_initial_schema
Create Date: 2026-08-16 18:50:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_github_integration"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add GitHub identity and installation fields to users table
    op.add_column("users", sa.Column("github_user_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("github_username", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("github_installation_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_users_github_user_id", "users", ["github_user_id"], unique=False)
    op.create_index("ix_users_github_username", "users", ["github_username"], unique=False)
    op.create_index("ix_users_github_installation_id", "users", ["github_installation_id"], unique=False)

    # 2. Add repository metadata fields to repositories table
    op.add_column("repositories", sa.Column("owner", sa.String(length=255), nullable=True))
    op.add_column("repositories", sa.Column("html_url", sa.String(length=1024), nullable=True))
    op.add_column("repositories", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("repositories", sa.Column("language", sa.String(length=100), nullable=True))

    # 3. Add branch metadata fields to repository_branches table
    op.add_column("repository_branches", sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    # 1. Remove branch metadata
    op.drop_column("repository_branches", "is_protected")

    # 2. Remove repository metadata
    op.drop_column("repositories", "language")
    op.drop_column("repositories", "description")
    op.drop_column("repositories", "html_url")
    op.drop_column("repositories", "owner")

    # 3. Remove user GitHub fields
    op.drop_index("ix_users_github_installation_id", table_name="users")
    op.drop_index("ix_users_github_username", table_name="users")
    op.drop_index("ix_users_github_user_id", table_name="users")
    op.drop_column("users", "github_installation_id")
    op.drop_column("users", "github_username")
    op.drop_column("users", "github_user_id")
