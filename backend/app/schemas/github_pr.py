"""Pydantic schemas for GitHub Webhooks and Pull Request Reviewer."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PRSnapshotResponse(BaseModel):
    """Schema representing an immutable snapshot of a GitHub Pull Request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_binding_id: uuid.UUID
    pr_number: int
    title: str
    body_summary: str | None = None
    author_username: str
    base_branch: str
    base_sha: str
    head_branch: str
    head_sha: str
    is_draft: bool = False
    changed_files_count: int = 0
    created_at: datetime.datetime


class PRReviewFindingResponse(BaseModel):
    """Schema representing an individual code review finding on a PR."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | str
    severity: str
    category: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    description: str
    evidence: str | None = None
    recommendation: str | None = None
    confidence: float | None = 1.0


class PRReviewTaskResponse(BaseModel):
    """Schema representing the status and results of a PR review task."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    snapshot_id: uuid.UUID
    snapshot: PRSnapshotResponse | None = None
    lifecycle_state: str
    active_agent: str = "REVIEWER"
    total_findings_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    findings: list[PRReviewFindingResponse] = Field(default_factory=list)
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    failure_reason: str | None = None


class WebhookAcceptedResponse(BaseModel):
    """Returned when a valid webhook delivery is accepted and queued."""

    status: str = "accepted"
    delivery_id: str
    event: str
    action: str | None = None
    task_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None


class RepositoryPullRequestsListResponse(BaseModel):
    """List of PR review tasks for a repository."""

    items: list[PRReviewTaskResponse]
    total: int
