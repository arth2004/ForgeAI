"""Drop unused encrypted_github_token from users

Revision ID: 0003_drop_github_token
Revises: 0002_github_integration
Create Date: 2026-08-16 19:25:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_drop_github_token"
down_revision: str | None = "0002_github_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop unused encrypted_github_token column (installation tokens are ephemeral and never persisted)
    op.drop_column("users", "encrypted_github_token")


def downgrade() -> None:
    op.add_column("users", sa.Column("encrypted_github_token", sa.Text(), nullable=True))
