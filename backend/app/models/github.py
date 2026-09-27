"""GitHub Pull Request Reviewer & Webhook Integration Models for Phase 7."""

import datetime
import enum
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDMixin, utc_now


class PRReviewLifecycleState(enum.StrEnum):
    """Lifecycle states for asynchronous GitHub Pull Request Review Tasks."""

    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    SNAPSHOTTING = "SNAPSHOTTING"
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    REVIEW_READY = "REVIEW_READY"
    SHA_VALIDATION = "SHA_VALIDATION"
    STALE = "STALE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class GitHubInstallation(Base, UUIDMixin, TimestampMixin):
    """Represents an authorized GitHub App installation bound to an Organization."""

    __tablename__ = "github_installations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )
    account_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    account_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Organization",
    )
    permissions: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=dict,
    )


class GitHubRepositoryBinding(Base, UUIDMixin, TimestampMixin):
    """Maps a GitHub repository to a Forge AI project repository."""

    __tablename__ = "github_repository_bindings"

    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    github_repo_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    auto_review_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    auto_review_drafts: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    min_severity_to_comment: Mapped[str] = mapped_column(
        String(16),
        default="LOW",
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("installation_id", "repository_id", name="uq_github_binding_inst_repo"),
    )


class PullRequestSnapshot(Base, UUIDMixin, TimestampMixin):
    """Immutable snapshot of a GitHub Pull Request at a specific head SHA."""

    __tablename__ = "pull_request_snapshots"

    repository_binding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_repository_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pr_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    body_summary: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    author_username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    base_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    base_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    head_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    head_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    is_draft: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    changed_files_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "repository_binding_id",
            "pr_number",
            "head_sha",
            name="uq_pr_snapshot_binding_pr_head",
        ),
    )


class PullRequestReviewTask(Base, UUIDMixin, TimestampMixin):
    """Tracks the multi-agent code review execution lifecycle for a PR snapshot."""

    __tablename__ = "pull_request_review_tasks"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pull_request_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    agent_review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(32),
        default=PRReviewLifecycleState.QUEUED.value,
        nullable=False,
        index=True,
    )
    active_agent: Mapped[str] = mapped_column(
        String(32),
        default="REVIEWER",
        nullable=False,
    )
    iteration_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_findings_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    critical_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    high_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=dict,
    )


class WebhookDelivery(Base, UUIDMixin):
    """Tracks unique GitHub webhook deliveries to prevent duplicate processing."""

    __tablename__ = "github_webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    action: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
    )
    repository_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    received_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
