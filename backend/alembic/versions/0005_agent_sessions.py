"""Create agent_sessions table for chat context binding

Revision ID: 0005_agent_sessions
Revises: 0004_repo_intelligence
Create Date: 2026-08-19 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_agent_sessions"
down_revision: str | None = "0004_repo_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["repository_branches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_sessions_id"),
        "agent_sessions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_sessions_user_id"),
        "agent_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_sessions_project_id"),
        "agent_sessions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_sessions_repository_id"),
        "agent_sessions",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_sessions_branch_id"),
        "agent_sessions",
        ["branch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_sessions_branch_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_repository_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_project_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_user_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
