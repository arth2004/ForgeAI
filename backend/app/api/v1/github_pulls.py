"""Read-only GitHub Pull Requests and Review Findings API for Phase 7B."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.models.agent import ReviewFinding
from app.models.auth import User
from app.models.github import (
    GitHubRepositoryBinding,
    PullRequestReviewTask,
    PullRequestSnapshot,
)
from app.schemas.github_pr import (
    PRReviewFindingResponse,
    PRReviewTaskResponse,
    PRSnapshotResponse,
    RepositoryPullRequestsListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/pulls/{snapshot_id}",
    response_model=PRReviewTaskResponse,
    summary="Get PR snapshot and review task status",
)
async def get_pull_request_review_task(
    snapshot_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PRReviewTaskResponse:
    """Retrieves the review status and findings summary for a specific PR snapshot."""
    snapshot = await db.get(PullRequestSnapshot, snapshot_id)
    if not snapshot:
        raise NotFoundException("PullRequestSnapshot", snapshot_id)

    task_q = (
        select(PullRequestReviewTask)
        .where(PullRequestReviewTask.snapshot_id == snapshot_id)
        .order_by(PullRequestReviewTask.created_at.desc())
    )
    task_res = await db.execute(task_q)
    task = task_res.scalars().first()

    if not task:
        raise NotFoundException("PullRequestReviewTask", f"snapshot_{snapshot_id}")

    findings_list: list[PRReviewFindingResponse] = []
    if task.agent_review_id:
        f_q = select(ReviewFinding).where(ReviewFinding.review_id == task.agent_review_id)
        f_res = await db.execute(f_q)
        for f in f_res.scalars().all():
            findings_list.append(
                PRReviewFindingResponse(
                    id=f.id,
                    severity=f.severity,
                    category=f.category,
                    file_path=f.file_path,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    description=f.description,
                    evidence=f.evidence,
                    recommendation=f.recommendation,
                )
            )

    return PRReviewTaskResponse(
        id=task.id,
        snapshot_id=snapshot.id,
        snapshot=PRSnapshotResponse.model_validate(snapshot),
        lifecycle_state=task.lifecycle_state,
        active_agent=task.active_agent,
        total_findings_count=task.total_findings_count,
        critical_count=task.critical_count,
        high_count=task.high_count,
        findings=findings_list,
        started_at=task.started_at,
        completed_at=task.completed_at,
        failure_reason=task.failure_reason,
    )


@router.get(
    "/pulls/{snapshot_id}/findings",
    response_model=list[PRReviewFindingResponse],
    summary="Get code review findings for a PR snapshot",
)
async def get_pull_request_findings(
    snapshot_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PRReviewFindingResponse]:
    """Retrieves all structured ReviewFinding entities associated with a PR review."""
    task_q = (
        select(PullRequestReviewTask)
        .where(PullRequestReviewTask.snapshot_id == snapshot_id)
        .order_by(PullRequestReviewTask.created_at.desc())
    )
    task_res = await db.execute(task_q)
    task = task_res.scalars().first()

    if not task or not task.agent_review_id:
        return []

    f_q = select(ReviewFinding).where(ReviewFinding.review_id == task.agent_review_id)
    f_res = await db.execute(f_q)
    return [
        PRReviewFindingResponse(
            id=f.id,
            severity=f.severity,
            category=f.category,
            file_path=f.file_path,
            start_line=f.start_line,
            end_line=f.end_line,
            description=f.description,
            evidence=f.evidence,
            recommendation=f.recommendation,
        )
        for f in f_res.scalars().all()
    ]


@router.get(
    "/repositories/{repository_id}/pulls",
    response_model=RepositoryPullRequestsListResponse,
    summary="List recent PR reviews for a repository",
)
async def list_repository_pull_request_reviews(
    repository_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RepositoryPullRequestsListResponse:
    """Lists all PR snapshots and review statuses for an indexed repository."""
    q = (
        select(PullRequestReviewTask, PullRequestSnapshot)
        .join(PullRequestSnapshot, PullRequestReviewTask.snapshot_id == PullRequestSnapshot.id)
        .join(GitHubRepositoryBinding, PullRequestSnapshot.repository_binding_id == GitHubRepositoryBinding.id)
        .where(GitHubRepositoryBinding.repository_id == repository_id)
        .order_by(PullRequestReviewTask.created_at.desc())
        .limit(50)
    )
    res = await db.execute(q)
    rows = res.all()

    items: list[PRReviewTaskResponse] = []
    for task, snapshot in rows:
        items.append(
            PRReviewTaskResponse(
                id=task.id,
                snapshot_id=snapshot.id,
                snapshot=PRSnapshotResponse.model_validate(snapshot),
                lifecycle_state=task.lifecycle_state,
                active_agent=task.active_agent,
                total_findings_count=task.total_findings_count,
                critical_count=task.critical_count,
                high_count=task.high_count,
                findings=[],
                started_at=task.started_at,
                completed_at=task.completed_at,
                failure_reason=task.failure_reason,
            )
        )

    return RepositoryPullRequestsListResponse(
        items=items,
        total=len(items),
    )
