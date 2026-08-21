"""Create agent_commits and agent_pull_requests tables for Phase 5D Git & GitHub Integration

Revision ID: 0008_agent_git_integration
Revises: 0007_agent_patches_and_tests
Create Date: 2026-08-22 04:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_agent_git_integration"
down_revision: str | None = "0007_agent_patches_and_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create agent_commits table
    op.create_table(
        "agent_commits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
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
            ["workspace_id"],
            ["agent_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
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
        op.f("ix_agent_commits_workspace_id"),
        "agent_commits",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_commits_session_id"),
        "agent_commits",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_commits_user_id"),
        "agent_commits",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_commits_commit_sha"),
        "agent_commits",
        ["commit_sha"],
        unique=False,
    )

    # 2. Create agent_pull_requests table
    op.create_table(
        "agent_pull_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("base_branch", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("github_pr_number", sa.Integer(), nullable=True),
        sa.Column("github_pr_url", sa.String(length=1024), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="READY"),
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
            ["workspace_id"],
            ["agent_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_pull_requests_workspace_id"),
        "agent_pull_requests",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_pull_requests_session_id"),
        "agent_pull_requests",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_pull_requests_repository_id"),
        "agent_pull_requests",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_pull_requests_status"),
        "agent_pull_requests",
        ["status"],
        unique=False,
    )

    # 3. Add Git columns to agent_workspaces
    op.add_column(
        "agent_workspaces",
        sa.Column("branch_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "agent_workspaces",
        sa.Column("current_commit_sha", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_workspaces",
        sa.Column("remote_branch_name", sa.String(length=255), nullable=True),
    )

    # 4. Add commit_id and pull_request_id to agent_approvals
    op.add_column(
        "agent_approvals",
        sa.Column("commit_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "agent_approvals",
        sa.Column("pull_request_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_approvals_commit_id",
        "agent_approvals",
        "agent_commits",
        ["commit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_approvals_pull_request_id",
        "agent_approvals",
        "agent_pull_requests",
        ["pull_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_agent_approvals_commit_id"),
        "agent_approvals",
        ["commit_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_approvals_pull_request_id"),
        "agent_approvals",
        ["pull_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_approvals_pull_request_id"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_commit_id"), table_name="agent_approvals")
    op.drop_constraint("fk_agent_approvals_pull_request_id", "agent_approvals", type_="foreignkey")
    op.drop_constraint("fk_agent_approvals_commit_id", "agent_approvals", type_="foreignkey")
    op.drop_column("agent_approvals", "pull_request_id")
    op.drop_column("agent_approvals", "commit_id")

    op.drop_column("agent_workspaces", "remote_branch_name")
    op.drop_column("agent_workspaces", "current_commit_sha")
    op.drop_column("agent_workspaces", "branch_name")

    op.drop_index(op.f("ix_agent_pull_requests_status"), table_name="agent_pull_requests")
    op.drop_index(op.f("ix_agent_pull_requests_repository_id"), table_name="agent_pull_requests")
    op.drop_index(op.f("ix_agent_pull_requests_session_id"), table_name="agent_pull_requests")
    op.drop_index(op.f("ix_agent_pull_requests_workspace_id"), table_name="agent_pull_requests")
    op.drop_table("agent_pull_requests")

    op.drop_index(op.f("ix_agent_commits_commit_sha"), table_name="agent_commits")
    op.drop_index(op.f("ix_agent_commits_user_id"), table_name="agent_commits")
    op.drop_index(op.f("ix_agent_commits_session_id"), table_name="agent_commits")
    op.drop_index(op.f("ix_agent_commits_workspace_id"), table_name="agent_commits")
    op.drop_table("agent_commits")
