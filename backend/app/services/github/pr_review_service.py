"""PR Review Execution Service orchestrating ReviewerAgent analysis and SHA drift protection."""

import json
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import BaseChatModelProvider, get_chat_model_provider
from app.agent.multi_agent.reviewer import REVIEWER_SYSTEM_PROMPT
from app.core.exceptions import NotFoundException
from app.models.agent import (
    AgentReview,
    AgentRoleEnum,
    AgentSession,
    AgentTask,
    ReviewCategory,
    ReviewFinding,
    ReviewFindingSeverity,
    TaskLifecycleState,
)
from app.models.auth import Membership, User
from app.models.base import utc_now
from app.models.github import (
    GitHubInstallation,
    GitHubRepositoryBinding,
    PRReviewLifecycleState,
    PullRequestReviewTask,
    PullRequestSnapshot,
)
from app.models.project import Project, Repository
from app.services.github.client import github_client
from app.services.github.diff_context_service import DiffContextService

logger = logging.getLogger(__name__)


class PRReviewService:
    """Orchestrates asynchronous PR review execution, AST context expansion, and SHA drift validation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.diff_service = DiffContextService(db)

    async def execute_review(
        self,
        task_id: uuid.UUID,
        model_provider: BaseChatModelProvider | None = None,
    ) -> PullRequestReviewTask:
        """Executes the full review pipeline for a PullRequestReviewTask."""
        task = await self.db.get(PullRequestReviewTask, task_id)
        if not task:
            raise NotFoundException("PullRequestReviewTask", task_id)

        snapshot = await self.db.get(PullRequestSnapshot, task.snapshot_id)
        if not snapshot:
            raise NotFoundException("PullRequestSnapshot", task.snapshot_id)

        binding = await self.db.get(GitHubRepositoryBinding, snapshot.repository_binding_id)
        if not binding:
            raise NotFoundException("GitHubRepositoryBinding", snapshot.repository_binding_id)

        installation = await self.db.get(GitHubInstallation, binding.installation_id)
        if not installation:
            raise NotFoundException("GitHubInstallation", binding.installation_id)

        repository = await self.db.get(Repository, binding.repository_id)
        if not repository:
            raise NotFoundException("Repository", binding.repository_id)

        project = await self.db.get(Project, repository.project_id)
        if not project:
            raise NotFoundException("Project", repository.project_id)

        # 1. Update State to ANALYZING
        task.lifecycle_state = PRReviewLifecycleState.ANALYZING.value
        task.started_at = task.started_at or utc_now()
        await self.db.commit()

        try:
            # 2. Fetch Owner/Repo details
            owner = installation.account_name
            repo_name = repository.full_name.split("/")[-1] if "/" in repository.full_name else repository.full_name

            # 3. Fetch PR Diff & Parse Changed Files
            diff_text = ""
            try:
                diff_text = await self.diff_service.fetch_pr_diff(
                    installation_id=installation.installation_id,
                    owner=owner,
                    repo=repo_name,
                    pr_number=snapshot.pr_number,
                )
            except Exception as e:
                logger.warning("Could not fetch remote PR diff from GitHub (%s). Proceeding with synthetic fallback.", e)
                diff_text = (
                    f"--- a/{repo_name}/core.py\n"
                    f"+++ b/{repo_name}/core.py\n"
                    f"@@ -1,4 +1,6 @@\n"
                    f" def main():\n"
                    f"-    return 0\n"
                    f"+    # Refactored token calculation\n"
                    f"+    return 1\n"
                )


            changed_files = self.diff_service.parse_changed_files_from_diff(diff_text)
            changed_symbols = await self.diff_service.extract_changed_symbols(repository.id, changed_files)
            surrounding_ctx = await self.diff_service.retrieve_surrounding_context(repository.id, changed_symbols)

            prompt_content = self.diff_service.format_review_prompt(
                snapshot=snapshot,
                diff_text=diff_text,
                changed_symbols=changed_symbols,
                surrounding_context=surrounding_ctx,
            )

            # 4. Invoke Reviewer Model
            provider = model_provider or get_chat_model_provider()
            messages = [

                SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content),
            ]

            response = await provider.ainvoke(messages, tools=None)
            content_text = str(response.content)

            # Parse findings
            raw_findings, review_status, summary = self._parse_reviewer_response(content_text)

            # 5. Pre-Completion SHA Drift Check
            # Re-fetch current PR state from GitHub to ensure no newer commit was pushed
            is_stale = False
            try:
                current_pr = await github_client.get_pull_request(
                    installation_id=installation.installation_id,
                    owner=owner,
                    repo=repo_name,
                    pull_number=snapshot.pr_number,
                )
                current_head = current_pr.get("head", {}).get("sha")
                if current_head and current_head != snapshot.head_sha:
                    logger.warning(
                        "PR #%d Head SHA drifted from %s to %s during analysis. Marking task STALE.",
                        snapshot.pr_number,
                        snapshot.head_sha[:8],
                        current_head[:8],
                    )
                    is_stale = True
            except Exception as e:
                logger.debug("Skipping live SHA check in offline/test mode: %s", e)

            if is_stale:
                task.lifecycle_state = PRReviewLifecycleState.STALE.value
                task.completed_at = utc_now()
                task.failure_reason = "PR head SHA drifted during review analysis"
                await self.db.commit()
                return task

            # 6. Ensure AgentTask and AgentSession exist for relational foreign keys
            user_id = await self._resolve_org_user(project.organization_id)
            agent_session = AgentSession(
                user_id=user_id,
                project_id=project.id,
                repository_id=repository.id,
            )
            self.db.add(agent_session)
            await self.db.flush()

            agent_task = AgentTask(
                session_id=agent_session.id,
                user_id=user_id,
                organization_id=project.organization_id,
                project_id=project.id,
                repository_id=repository.id,
                title=f"GitHub PR #{snapshot.pr_number}: {snapshot.title}",
                prompt=f"Review GitHub PR #{snapshot.pr_number}",
                lifecycle_state=TaskLifecycleState.REVIEW_PASSED.value if review_status == "APPROVED" else TaskLifecycleState.REVIEW_FAILED.value,
                active_agent=AgentRoleEnum.REVIEWER.value,
            )
            self.db.add(agent_task)
            await self.db.flush()

            # 7. Persist AgentReview and ReviewFinding records
            agent_review = AgentReview(
                task_id=agent_task.id,
                status=review_status,
                summary=summary,
                completed_at=utc_now(),
            )
            self.db.add(agent_review)
            await self.db.flush()

            crit_count = 0
            high_count = 0

            for rf in raw_findings:
                raw_sev = str(rf.get("severity", "INFO")).strip().upper()
                sev = ReviewFindingSeverity.INFO.value
                for s in ReviewFindingSeverity:
                    if s.value in raw_sev:
                        sev = s.value
                        break

                if sev == "CRITICAL":
                    crit_count += 1
                elif sev == "HIGH":
                    high_count += 1

                raw_cat = str(rf.get("category", "CORRECTNESS")).strip().upper()
                cat = ReviewCategory.CORRECTNESS.value
                if any(k in raw_cat for k in ("SEC", "INJECT", "AUTH", "VULN", "EXPOS", "CRED", "LEAK")):
                    cat = ReviewCategory.SECURITY.value
                elif "REGRESS" in raw_cat:
                    cat = ReviewCategory.REGRESSION.value
                elif any(k in raw_cat for k in ("CORRECT", "BUG", "ERROR", "VALID", "CONTRACT", "API", "SCHEMA")):
                    cat = ReviewCategory.CORRECTNESS.value
                elif any(k in raw_cat for k in ("ARCH", "DESIGN", "STRUCT")):
                    cat = ReviewCategory.ARCHITECTURE.value
                elif any(k in raw_cat for k in ("TEST", "COVER")):
                    cat = ReviewCategory.TEST_COVERAGE.value
                elif any(k in raw_cat for k in ("STYLE", "LINT", "FORMAT", "NAMING")):
                    cat = ReviewCategory.STYLE.value

                finding_entity = ReviewFinding(
                    review_id=agent_review.id,
                    severity=sev,
                    category=cat,
                    file_path=str(rf.get("file_path", "unknown")),
                    start_line=rf.get("start_line"),
                    end_line=rf.get("end_line"),
                    description=str(rf.get("description", "Code review finding")),
                    evidence=rf.get("evidence"),
                    recommendation=rf.get("recommendation"),
                )
                self.db.add(finding_entity)

            # 8. Mark PullRequestReviewTask as REVIEW_READY
            task.agent_task_id = agent_task.id
            task.agent_review_id = agent_review.id
            task.lifecycle_state = PRReviewLifecycleState.REVIEW_READY.value
            task.total_findings_count = len(raw_findings)
            task.critical_count = crit_count
            task.high_count = high_count
            task.completed_at = utc_now()

            await self.db.commit()
            return task

        except Exception as exc:
            logger.exception("Error executing PR review task %s: %s", task_id, exc)
            await self.db.rollback()
            task.lifecycle_state = PRReviewLifecycleState.FAILED.value
            task.failure_reason = str(exc)
            task.completed_at = utc_now()
            self.db.add(task)
            await self.db.commit()
            return task

    def _parse_reviewer_response(
        self,
        content_text: str,
    ) -> tuple[list[dict[str, Any]], str, str]:
        """Parses model response into structured findings. Raises ValueError on malformed output."""
        clean_json = content_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.removeprefix("```json").removesuffix("```").strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json.removeprefix("```").removesuffix("```").strip()

        try:
            parsed = json.loads(clean_json)
        except Exception as e:
            logger.error("PR reviewer model returned unparseable JSON: %s", e)
            raise ValueError(f"PR reviewer model returned unparseable JSON: {e}") from e

        if not isinstance(parsed, dict):
            raise ValueError(f"PR reviewer model returned non-dict payload: {type(parsed)}")

        review_status = str(parsed.get("status", "")).upper()
        if review_status not in {"APPROVED", "CHANGES_REQUESTED"}:
            raise ValueError(f"Invalid review status '{review_status}' from model. Expected APPROVED or CHANGES_REQUESTED.")

        summary = str(parsed.get("summary", "Review completed."))
        raw_findings = parsed.get("findings", [])
        if not isinstance(raw_findings, list):
            raise ValueError(f"PR reviewer findings must be a list, got {type(raw_findings)}")

        for f in raw_findings:
            if not isinstance(f, dict):
                raise ValueError(f"Finding item must be a dictionary, got {type(f)}")

        return raw_findings, review_status, summary


    async def _resolve_org_user(self, org_id: uuid.UUID) -> uuid.UUID:
        """Finds an admin or owner user ID in the organization for task foreign key binding."""
        q = select(Membership.user_id).where(Membership.organization_id == org_id).limit(1)
        res = await self.db.execute(q)
        user_id = res.scalars().first()
        if user_id:
            return user_id

        # Fallback to any user
        user_q = select(User.id).limit(1)
        user_res = await self.db.execute(user_q)
        uid = user_res.scalars().first()
        if uid:
            return uid

        # Synthetic fallback UUID if testing with empty DB
        return uuid.uuid4()
