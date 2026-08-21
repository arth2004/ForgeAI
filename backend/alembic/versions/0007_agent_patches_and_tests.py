"""Create agent_patches and agent_test_executions tables for Phase 5C

Revision ID: 0007_agent_patches_and_tests
Revises: 0006_agent_workspaces_and_approvals
Create Date: 2026-08-22 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_agent_patches_and_tests"
down_revision: str | None = "0006_agent_workspaces_and_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create agent_patches table
    op.create_table(
        "agent_patches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PROPOSED"),
        sa.Column("summary", sa.String(length=1024), nullable=False),
        sa.Column(
            "files",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("diff_content", sa.String(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
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
        op.f("ix_agent_patches_id"),
        "agent_patches",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_patches_workspace_id"),
        "agent_patches",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_patches_session_id"),
        "agent_patches",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_patches_user_id"),
        "agent_patches",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_patches_status"),
        "agent_patches",
        ["status"],
        unique=False,
    )

    # 2. Add patch_id and rejection_reason to agent_approvals table
    op.add_column("agent_approvals", sa.Column("patch_id", sa.Uuid(), nullable=True))
    op.add_column("agent_approvals", sa.Column("rejection_reason", sa.String(length=1024), nullable=True))
    op.create_foreign_key(
        "fk_agent_approvals_patch_id",
        "agent_approvals",
        "agent_patches",
        ["patch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_agent_approvals_patch_id"),
        "agent_approvals",
        ["patch_id"],
        unique=False,
    )

    # 3. Create agent_test_executions table
    op.create_table(
        "agent_test_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("patch_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "test_command",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.String(), nullable=True),
        sa.Column("stderr", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["patch_id"],
            ["agent_patches.id"],
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
        op.f("ix_agent_test_executions_id"),
        "agent_test_executions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_test_executions_workspace_id"),
        "agent_test_executions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_test_executions_session_id"),
        "agent_test_executions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_test_executions_patch_id"),
        "agent_test_executions",
        ["patch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_test_executions_user_id"),
        "agent_test_executions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_test_executions_status"),
        "agent_test_executions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_test_executions_status"), table_name="agent_test_executions")
    op.drop_index(op.f("ix_agent_test_executions_user_id"), table_name="agent_test_executions")
    op.drop_index(op.f("ix_agent_test_executions_patch_id"), table_name="agent_test_executions")
    op.drop_index(op.f("ix_agent_test_executions_session_id"), table_name="agent_test_executions")
    op.drop_index(op.f("ix_agent_test_executions_workspace_id"), table_name="agent_test_executions")
    op.drop_index(op.f("ix_agent_test_executions_id"), table_name="agent_test_executions")
    op.drop_table("agent_test_executions")

    op.drop_index(op.f("ix_agent_approvals_patch_id"), table_name="agent_approvals")
    op.drop_constraint("fk_agent_approvals_patch_id", "agent_approvals", type_="foreignkey")
    op.drop_column("agent_approvals", "rejection_reason")
    op.drop_column("agent_approvals", "patch_id")

    op.drop_index(op.f("ix_agent_patches_status"), table_name="agent_patches")
    op.drop_index(op.f("ix_agent_patches_user_id"), table_name="agent_patches")
    op.drop_index(op.f("ix_agent_patches_session_id"), table_name="agent_patches")
    op.drop_index(op.f("ix_agent_patches_workspace_id"), table_name="agent_patches")
    op.drop_index(op.f("ix_agent_patches_id"), table_name="agent_patches")
    op.drop_table("agent_patches")
