"""Create agent_workspaces and agent_approvals tables for Phase 5B

Revision ID: 0006_agent_workspaces_and_approvals
Revises: 0005_agent_sessions
Create Date: 2026-08-22 03:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_agent_workspaces_and_approvals"
down_revision: str | None = "0005_agent_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create agent_workspaces
    op.create_table(
        "agent_workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("base_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["session_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
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
            ["branch_id"],
            ["repository_branches.id"],
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
        op.f("ix_agent_workspaces_id"),
        "agent_workspaces",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_session_id"),
        "agent_workspaces",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_organization_id"),
        "agent_workspaces",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_project_id"),
        "agent_workspaces",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_repository_id"),
        "agent_workspaces",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_branch_id"),
        "agent_workspaces",
        ["branch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_user_id"),
        "agent_workspaces",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_workspaces_status"),
        "agent_workspaces",
        ["status"],
        unique=False,
    )

    # 2. Create agent_approvals
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("approval_type", sa.String(length=32), nullable=False, server_default="PLAN"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column(
            "plan_payload",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            ["session_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["agent_workspaces.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_approvals_id"),
        "agent_approvals",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_session_id"),
        "agent_approvals",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_workspace_id"),
        "agent_approvals",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_user_id"),
        "agent_approvals",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_approval_type"),
        "agent_approvals",
        ["approval_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_status"),
        "agent_approvals",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop agent_approvals
    op.drop_index(op.f("ix_agent_approvals_status"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_approval_type"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_user_id"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_workspace_id"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_session_id"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_id"), table_name="agent_approvals")
    op.drop_table("agent_approvals")

    # Drop agent_workspaces
    op.drop_index(op.f("ix_agent_workspaces_status"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_user_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_branch_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_repository_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_project_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_organization_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_session_id"), table_name="agent_workspaces")
    op.drop_index(op.f("ix_agent_workspaces_id"), table_name="agent_workspaces")
    op.drop_table("agent_workspaces")
