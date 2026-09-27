"""PR Ingestion Service for processing and persisting verified GitHub Webhook events."""

import logging
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, UnauthorizedException
from app.models.base import utc_now
from app.models.github import (
    GitHubInstallation,
    GitHubRepositoryBinding,
    PRReviewLifecycleState,
    PullRequestReviewTask,
    PullRequestSnapshot,
    WebhookDelivery,
)
from app.models.project import Repository
from app.services.github.sanitizer import sanitize_pr_text

logger = logging.getLogger(__name__)


class PRIngestionService:
    """Handles GitHub webhook delivery deduplication, repository binding, and immutable PR snapshot creation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_delivery(
        self,
        delivery_id: str,
        event_type: str,
        action: str | None = None,
        repository_id: int | None = None,
    ) -> bool:
        """Records a webhook delivery UUID. Returns True if newly registered, False if duplicate."""
        existing_q = select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
        res = await self.db.execute(existing_q)
        if res.scalars().first():
            logger.info("Webhook delivery %s already processed. Skipping duplicate.", delivery_id)
            return False

        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repository_id=repository_id,
            received_at=utc_now(),
        )
        self.db.add(delivery)
        await self.db.flush()
        return True

    async def resolve_binding(
        self,
        installation_id: int,
        github_repo_id: int,
    ) -> tuple[GitHubInstallation, GitHubRepositoryBinding, Repository]:
        """Resolves GitHub installation and repository mapping to Forge AI tenant models."""
        inst_q = select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        inst_res = await self.db.execute(inst_q)
        installation = inst_res.scalars().first()

        if not installation:
            logger.warning("Unknown GitHub installation ID: %s", installation_id)
            raise UnauthorizedException(f"GitHub installation {installation_id} is not registered.")

        bind_q = (
            select(GitHubRepositoryBinding, Repository)
            .join(Repository, GitHubRepositoryBinding.repository_id == Repository.id)
            .where(
                GitHubRepositoryBinding.installation_id == installation.id,
                GitHubRepositoryBinding.github_repo_id == github_repo_id,
                GitHubRepositoryBinding.is_active.is_(True),
            )
        )
        bind_res = await self.db.execute(bind_q)
        row = bind_res.first()

        if not row:
            logger.warning(
                "No active repository binding for GitHub repo %s under installation %s",
                github_repo_id,
                installation_id,
            )
            raise NotFoundException("GitHubRepositoryBinding", f"repo_{github_repo_id}")

        binding, repo = row
        return installation, binding, repo

    async def ingest_pull_request_event(
        self,
        payload: dict[str, Any],
        delivery_id: str,
    ) -> tuple[PullRequestSnapshot, PullRequestReviewTask] | None:
        """Processes a pull_request event, snapshotting head/base SHAs and queuing analysis."""
        action = payload.get("action")
        pr_data = payload.get("pull_request")
        if not pr_data:
            logger.warning("Pull request event missing 'pull_request' payload.")
            return None

        installation_id = payload.get("installation", {}).get("id")
        github_repo_id = payload.get("repository", {}).get("id")

        if not installation_id or not github_repo_id:
            logger.warning("Pull request webhook missing installation or repository ID.")
            return None

        # Resolve tenant binding
        installation, binding, repo = await self.resolve_binding(installation_id, github_repo_id)

        pr_number = int(pr_data["number"])
        title = sanitize_pr_text(pr_data.get("title", f"Pull Request #{pr_number}"))
        body_summary = sanitize_pr_text(pr_data.get("body", ""))
        author_username = pr_data.get("user", {}).get("login", "unknown")
        base_branch = pr_data.get("base", {}).get("ref", "main")
        base_sha = pr_data.get("base", {}).get("sha", "")
        head_branch = pr_data.get("head", {}).get("ref", "")
        head_sha = pr_data.get("head", {}).get("sha", "")
        is_draft = bool(pr_data.get("draft", False))
        changed_files_count = int(pr_data.get("changed_files", 0))

        if action == "closed":
            logger.info("PR #%d closed. Marking active review tasks as CANCELLED.", pr_number)
            await self._mark_pr_tasks_stale(binding.id, pr_number, final_state=PRReviewLifecycleState.FAILED.value)
            return None

        # If synchronize event, mark any older in-flight review tasks as STALE
        if action == "synchronize":
            logger.info(
                "PR #%d synchronized to new SHA %s. Marking older review tasks as STALE.",
                pr_number,
                head_sha[:8],
            )
            await self._mark_pr_tasks_stale(binding.id, pr_number, final_state=PRReviewLifecycleState.STALE.value)

        # 1. Create or retrieve PullRequestSnapshot
        snap_q = select(PullRequestSnapshot).where(
            PullRequestSnapshot.repository_binding_id == binding.id,
            PullRequestSnapshot.pr_number == pr_number,
            PullRequestSnapshot.head_sha == head_sha,
        )
        snap_res = await self.db.execute(snap_q)
        snapshot = snap_res.scalars().first()

        if not snapshot:
            snapshot = PullRequestSnapshot(
                repository_binding_id=binding.id,
                pr_number=pr_number,
                title=title,
                body_summary=body_summary,
                author_username=author_username,
                base_branch=base_branch,
                base_sha=base_sha,
                head_branch=head_branch,
                head_sha=head_sha,
                is_draft=is_draft,
                changed_files_count=changed_files_count,
            )
            self.db.add(snapshot)
            await self.db.flush()

        # 2. Check if a task already exists for this snapshot
        task_q = select(PullRequestReviewTask).where(
            PullRequestReviewTask.snapshot_id == snapshot.id,
        ).order_by(PullRequestReviewTask.created_at.desc())
        task_res = await self.db.execute(task_q)
        review_task = task_res.scalars().first()

        if not review_task or review_task.lifecycle_state in (PRReviewLifecycleState.FAILED.value, PRReviewLifecycleState.REJECTED.value):
            review_task = PullRequestReviewTask(
                snapshot_id=snapshot.id,
                lifecycle_state=PRReviewLifecycleState.QUEUED.value,
                active_agent="REVIEWER",
                started_at=utc_now(),
            )
            self.db.add(review_task)
            await self.db.flush()

        await self.db.commit()
        return snapshot, review_task

    async def _mark_pr_tasks_stale(
        self,
        binding_id: uuid.UUID,
        pr_number: int,
        final_state: str = PRReviewLifecycleState.STALE.value,
    ) -> None:
        """Transitions previous review tasks for the same PR to a terminal stale or cancelled state."""
        subq = (
            select(PullRequestSnapshot.id)
            .where(
                PullRequestSnapshot.repository_binding_id == binding_id,
                PullRequestSnapshot.pr_number == pr_number,
            )
        )
        stmt = (
            update(PullRequestReviewTask)
            .where(
                PullRequestReviewTask.snapshot_id.in_(subq),
                PullRequestReviewTask.lifecycle_state.in_([
                    PRReviewLifecycleState.RECEIVED.value,
                    PRReviewLifecycleState.VALIDATING.value,
                    PRReviewLifecycleState.SNAPSHOTTING.value,
                    PRReviewLifecycleState.QUEUED.value,
                    PRReviewLifecycleState.ANALYZING.value,
                    PRReviewLifecycleState.REVIEW_READY.value,
                ]),
            )
            .values(
                lifecycle_state=final_state,
                completed_at=utc_now(),
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
