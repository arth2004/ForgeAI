import datetime
import enum
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDMixin


class WorkspaceStatus(enum.StrEnum):
    CREATED = "CREATED"
    PREPARED = "PREPARED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DESTROYED = "DESTROYED"
    FAILED = "FAILED"


class ApprovalType(enum.StrEnum):
    PLAN = "PLAN"
    DIFF = "DIFF"
    COMMIT = "COMMIT"
    PUSH = "PUSH"
    PR_CREATE = "PR_CREATE"


class ApprovalStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PatchStatus(enum.StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class PatchOperation(enum.StrEnum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


class TestExecutionStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"


class PullRequestStatus(enum.StrEnum):
    READY = "READY"
    CREATED = "CREATED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class AgentSession(Base, UUIDMixin, TimestampMixin):
    """Represents the operational context binding for an agent chat session."""

    __tablename__ = "agent_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )


class AgentWorkspace(Base, UUIDMixin, TimestampMixin):
    """Represents an isolated, ephemeral workspace for an agent session."""

    __tablename__ = "agent_workspaces"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_branches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=WorkspaceStatus.CREATED.value,
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    base_commit_sha: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    branch_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    current_commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
    )
    remote_branch_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    destroyed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AgentPatch(Base, UUIDMixin, TimestampMixin):
    """Represents a structured, atomic patch proposal for an ephemeral workspace."""

    __tablename__ = "agent_patches"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=PatchStatus.PROPOSED.value,
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    files: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    diff_content: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    applied_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AgentCommit(Base, UUIDMixin, TimestampMixin):
    """Represents an approved, recorded Git commit created within an ephemeral workspace."""

    __tablename__ = "agent_commits"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )


class AgentPullRequest(Base, UUIDMixin, TimestampMixin):
    """Represents a GitHub Pull Request proposed and created through human approval."""

    __tablename__ = "agent_pull_requests"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    base_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    github_pr_number: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )
    github_pr_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=PullRequestStatus.READY.value,
        nullable=False,
        index=True,
    )


class AgentApproval(Base, UUIDMixin, TimestampMixin):
    """Represents a human-in-the-loop approval gate for agent actions."""

    __tablename__ = "agent_approvals"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_patches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    commit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_commits.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pull_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_pull_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_type: Mapped[str] = mapped_column(
        String(32),
        default=ApprovalType.PLAN.value,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=ApprovalStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    plan_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=None,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AgentTestExecution(Base, UUIDMixin, TimestampMixin):
    """Represents a sandboxed test execution record within an ephemeral workspace."""

    __tablename__ = "agent_test_executions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_patches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_command: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=TestExecutionStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    exit_code: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )
    stdout: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    stderr: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
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


class TaskLifecycleState(enum.StrEnum):
    TASK_CREATED = "TASK_CREATED"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"
    WORKSPACE_READY = "WORKSPACE_READY"
    IMPLEMENTING = "IMPLEMENTING"
    PATCH_READY = "PATCH_READY"
    WAITING_DIFF_APPROVAL = "WAITING_DIFF_APPROVAL"
    TESTING = "TESTING"
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    CODING_REPAIR = "CODING_REPAIR"
    REVIEWING = "REVIEWING"
    REVIEW_PASSED = "REVIEW_PASSED"
    REVIEW_FAILED = "REVIEW_FAILED"
    WAITING_COMMIT_APPROVAL = "WAITING_COMMIT_APPROVAL"
    COMMITTED = "COMMITTED"
    WAITING_PUSH_APPROVAL = "WAITING_PUSH_APPROVAL"
    PUSHED = "PUSHED"
    WAITING_PR_APPROVAL = "WAITING_PR_APPROVAL"
    PR_CREATED = "PR_CREATED"
    COMPLETED = "COMPLETED"
    WAITING_HUMAN_INTERVENTION = "WAITING_HUMAN_INTERVENTION"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRoleEnum(enum.StrEnum):
    SUPERVISOR = "SUPERVISOR"
    PLANNER = "PLANNER"
    CODER = "CODER"
    TESTER = "TESTER"
    REVIEWER = "REVIEWER"


class ReviewFindingSeverity(enum.StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReviewCategory(enum.StrEnum):
    SECURITY = "SECURITY"
    REGRESSION = "REGRESSION"
    CORRECTNESS = "CORRECTNESS"
    ARCHITECTURE = "ARCHITECTURE"
    STYLE = "STYLE"
    TEST_COVERAGE = "TEST_COVERAGE"


class AgentTask(Base, UUIDMixin, TimestampMixin):
    """Tracks top-level multi-agent engineering task orchestration lifecycle."""

    __tablename__ = "agent_tasks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(64),
        default=TaskLifecycleState.TASK_CREATED.value,
        nullable=False,
        index=True,
    )
    active_agent: Mapped[str] = mapped_column(
        String(32),
        default=AgentRoleEnum.SUPERVISOR.value,
        nullable=False,
    )
    iteration_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    tool_call_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
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
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AgentReview(Base, UUIDMixin, TimestampMixin):
    """Stores structured code review reports produced by the Reviewer Agent."""

    __tablename__ = "agent_reviews"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_patches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="APPROVED",
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class ReviewFinding(Base, UUIDMixin, TimestampMixin):
    """Individual structured defect/security finding associated with an AgentReview."""

    __tablename__ = "agent_review_findings"

    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        default=ReviewFindingSeverity.INFO.value,
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(32),
        default=ReviewCategory.CORRECTNESS.value,
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    start_line: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )
    end_line: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )
    description: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    evidence: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )
    recommendation: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        default=None,
    )




