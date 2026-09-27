"""Create github_installations, github_repository_bindings, pull_request_snapshots, pull_request_review_tasks, and github_webhook_deliveries tables for Phase 7B GitHub PR Reviewer.

Revision ID: 0010_github_pr_reviewer
Revises: 0009_agent_task_and_review
Create Date: 2026-08-26 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_github_pr_reviewer"
down_revision: str | None = "0009_agent_task_and_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create github_installations table
    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False, server_default="Organization"),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", name="uq_github_installations_inst_id"),
    )
    op.create_index(
        op.f("ix_github_installations_organization_id"),
        "github_installations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_installations_installation_id"),
        "github_installations",
        ["installation_id"],
        unique=True,
    )

    # 2. Create github_repository_bindings table
    op.create_table(
        "github_repository_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_review_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_review_drafts", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("min_severity_to_comment", sa.String(length=16), nullable=False, server_default="LOW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["github_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", "repository_id", name="uq_github_binding_inst_repo"),
    )
    op.create_index(
        op.f("ix_github_repository_bindings_installation_id"),
        "github_repository_bindings",
        ["installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_repository_bindings_repository_id"),
        "github_repository_bindings",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_repository_bindings_github_repo_id"),
        "github_repository_bindings",
        ["github_repo_id"],
        unique=False,
    )

    # 3. Create pull_request_snapshots table
    op.create_table(
        "pull_request_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_binding_id", sa.Uuid(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body_summary", sa.String(), nullable=True),
        sa.Column("author_username", sa.String(length=255), nullable=False),
        sa.Column("base_branch", sa.String(length=255), nullable=False),
        sa.Column("base_sha", sa.String(length=40), nullable=False),
        sa.Column("head_branch", sa.String(length=255), nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("changed_files_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_binding_id"], ["github_repository_bindings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_binding_id",
            "pr_number",
            "head_sha",
            name="uq_pr_snapshot_binding_pr_head",
        ),
    )
    op.create_index(
        op.f("ix_pull_request_snapshots_repository_binding_id"),
        "pull_request_snapshots",
        ["repository_binding_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pull_request_snapshots_pr_number"),
        "pull_request_snapshots",
        ["pr_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pull_request_snapshots_head_sha"),
        "pull_request_snapshots",
        ["head_sha"],
        unique=False,
    )

    # 4. Create pull_request_review_tasks table
    op.create_table(
        "pull_request_review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("agent_task_id", sa.Uuid(), nullable=True),
        sa.Column("agent_review_id", sa.Uuid(), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("active_agent", sa.String(length=32), nullable=False, server_default="REVIEWER"),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["pull_request_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_review_id"], ["agent_reviews.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pull_request_review_tasks_snapshot_id"),
        "pull_request_review_tasks",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pull_request_review_tasks_lifecycle_state"),
        "pull_request_review_tasks",
        ["lifecycle_state"],
        unique=False,
    )

    # 5. Create github_webhook_deliveries table
    op.create_table(
        "github_webhook_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("repository_id", sa.BigInteger(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", name="uq_github_webhook_deliveries_delivery_id"),
    )
    op.create_index(
        op.f("ix_github_webhook_deliveries_delivery_id"),
        "github_webhook_deliveries",
        ["delivery_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_github_webhook_deliveries_event_type"),
        "github_webhook_deliveries",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("github_webhook_deliveries")
    op.drop_table("pull_request_review_tasks")
    op.drop_table("pull_request_snapshots")
    op.drop_table("github_repository_bindings")
    op.drop_table("github_installations")
