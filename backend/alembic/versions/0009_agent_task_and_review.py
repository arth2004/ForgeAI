"""Create agent_tasks, agent_reviews, and agent_review_findings tables for Phase 6B Multi-Agent Engineering Runtime

Revision ID: 0009_agent_task_and_review
Revises: 0008_agent_git_integration
Create Date: 2026-08-24 00:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_agent_task_and_review"
down_revision: str | None = "0008_agent_git_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create agent_tasks table
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=64), nullable=False),
        sa.Column("active_agent", sa.String(length=32), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["repository_branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["agent_workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_tasks_branch_id"), "agent_tasks", ["branch_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_lifecycle_state"), "agent_tasks", ["lifecycle_state"], unique=False)
    op.create_index(op.f("ix_agent_tasks_organization_id"), "agent_tasks", ["organization_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_project_id"), "agent_tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_repository_id"), "agent_tasks", ["repository_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_session_id"), "agent_tasks", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_user_id"), "agent_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_workspace_id"), "agent_tasks", ["workspace_id"], unique=False)

    # 2. Create agent_reviews table
    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("patch_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patch_id"], ["agent_patches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_reviews_patch_id"), "agent_reviews", ["patch_id"], unique=False)
    op.create_index(op.f("ix_agent_reviews_status"), "agent_reviews", ["status"], unique=False)
    op.create_index(op.f("ix_agent_reviews_task_id"), "agent_reviews", ["task_id"], unique=False)

    # 3. Create agent_review_findings table
    op.create_table(
        "agent_review_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("evidence", sa.String(), nullable=True),
        sa.Column("recommendation", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(["review_id"], ["agent_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_review_findings_category"), "agent_review_findings", ["category"], unique=False)
    op.create_index(op.f("ix_agent_review_findings_review_id"), "agent_review_findings", ["review_id"], unique=False)
    op.create_index(op.f("ix_agent_review_findings_severity"), "agent_review_findings", ["severity"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_review_findings_severity"), table_name="agent_review_findings")
    op.drop_index(op.f("ix_agent_review_findings_review_id"), table_name="agent_review_findings")
    op.drop_index(op.f("ix_agent_review_findings_category"), table_name="agent_review_findings")
    op.drop_table("agent_review_findings")

    op.drop_index(op.f("ix_agent_reviews_task_id"), table_name="agent_reviews")
    op.drop_index(op.f("ix_agent_reviews_status"), table_name="agent_reviews")
    op.drop_index(op.f("ix_agent_reviews_patch_id"), table_name="agent_reviews")
    op.drop_table("agent_reviews")

    op.drop_index(op.f("ix_agent_tasks_workspace_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_user_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_session_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_repository_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_project_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_organization_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_lifecycle_state"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_branch_id"), table_name="agent_tasks")
    op.drop_table("agent_tasks")
