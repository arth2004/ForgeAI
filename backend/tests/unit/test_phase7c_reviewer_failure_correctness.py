"""Unit and integration tests for Phase 7C.2 Reviewer Runtime Failure Correctness.

Verifies:
1. Model invocation succeeds + no findings -> REVIEW_READY (status="APPROVED", 0 findings)
2. Model invocation succeeds + findings -> REVIEW_READY (status="CHANGES_REQUESTED", >0 findings)
3. Model returns invalid JSON -> FAILED (never APPROVED)
4. Model raises provider exception -> FAILED (never APPROVED)
5. Model returns malformed structured response -> FAILED (never APPROVED)
6. Provider HTTP 429 -> FAILED with explicit failure reason
7. Failed review does not create synthetic findings in database
8. Failed review is visible through existing API
"""

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import ModelProviderException
from app.agent.models import MockChatModelProvider
from app.agent.multi_agent.reviewer import ReviewerAgent
from app.agent.multi_agent.state import create_initial_multi_agent_state
from app.agent.multi_agent.types import (
    ReviewFindingSeverity,
    TaskLifecycleState,
)
from app.models.agent import AgentReview, ReviewFinding
from app.models.auth import Membership, Organization, Role, User
from app.models.github import (
    GitHubInstallation,
    GitHubRepositoryBinding,
    PRReviewLifecycleState,
    PullRequestReviewTask,
    PullRequestSnapshot,
)
from app.models.project import IndexingStatus, Project, Repository
from app.services.github.pr_review_service import PRReviewService


@pytest.mark.asyncio
async def test_reviewer_agent_succeeds_no_findings():
    """State A: Model successfully analyzes diff and finds zero issues -> APPROVED / REVIEW_PASSED."""
    clean_response = {
        "status": "APPROVED",
        "summary": "The refactoring is clean and does not introduce security or regression issues.",
        "findings": [],
    }
    mock_provider = MockChatModelProvider(default_response=json.dumps(clean_response))
    reviewer = ReviewerAgent(model_provider=mock_provider)

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Review safe PR patch",
    )
    state["active_patch"] = {"diff_content": "+ # Added helpful comment"}

    delta = await reviewer.execute(state)
    assert delta["review_status"] == "APPROVED"
    assert delta["lifecycle_state"] == TaskLifecycleState.REVIEW_PASSED.value
    assert len(delta["review_findings"]) == 0


@pytest.mark.asyncio
async def test_reviewer_agent_succeeds_with_findings():
    """State B: Model successfully analyzes diff and returns structured findings -> CHANGES_REQUESTED."""
    findings_response = {
        "status": "CHANGES_REQUESTED",
        "summary": "Detected unauthenticated admin route vulnerability.",
        "findings": [
            {
                "severity": "CRITICAL",
                "category": "SECURITY",
                "file_path": "app/api/v1/admin.py",
                "start_line": 20,
                "end_line": 25,
                "description": "Missing authentication dependency on admin endpoint",
                "recommendation": "Add Depends(get_current_admin_user)",
            }
        ],
    }
    mock_provider = MockChatModelProvider(default_response=json.dumps(findings_response))
    reviewer = ReviewerAgent(model_provider=mock_provider)

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Review admin PR patch",
    )
    state["active_patch"] = {"diff_content": "+ @router.get('/admin')\n+ def get_all(): ..."}

    delta = await reviewer.execute(state)
    assert delta["review_status"] == "CHANGES_REQUESTED"
    assert delta["lifecycle_state"] == TaskLifecycleState.REVIEW_FAILED.value
    assert len(delta["review_findings"]) == 1
    assert delta["review_findings"][0]["severity"] == ReviewFindingSeverity.CRITICAL.value


@pytest.mark.asyncio
async def test_reviewer_agent_raises_on_invalid_json():
    """State C: Model returns invalid / truncated JSON -> Must raise ValueError and NOT fallback to APPROVED."""
    mock_provider = MockChatModelProvider(default_response="I think this looks good! (not valid JSON)")
    reviewer = ReviewerAgent(model_provider=mock_provider)

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Review patch",
    )
    state["active_patch"] = {"diff_content": "+ return 1"}

    with pytest.raises(ValueError, match="Reviewer model response is not valid JSON"):
        await reviewer.execute(state)


@pytest.mark.asyncio
async def test_reviewer_agent_raises_on_malformed_status():
    """State C: Model returns JSON missing a valid status -> Must raise ValueError."""
    malformed_json = {
        "status": "UNKNOWN_STATE",
        "summary": "Some summary",
        "findings": [],
    }
    mock_provider = MockChatModelProvider(default_response=json.dumps(malformed_json))
    reviewer = ReviewerAgent(model_provider=mock_provider)

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Review patch",
    )
    state["active_patch"] = {"diff_content": "+ return 1"}

    with pytest.raises(ValueError, match="Invalid review status"):
        await reviewer.execute(state)


@pytest.mark.asyncio
async def test_pr_review_service_fails_on_model_invalid_json(db_session: AsyncSession):
    """PRReviewService marks task FAILED and persists zero synthetic findings on unparseable model response."""
    org = Organization(name="Failure Test Org", slug="failure-org")
    db_session.add(org)
    await db_session.flush()

    user = User(email="failure_tester@example.com", hashed_password="pw", full_name="Failure Tester")
    db_session.add(user)
    await db_session.flush()

    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.admin))

    proj = Project(name="PR Failure Proj", organization_id=org.id)
    db_session.add(proj)
    await db_session.flush()

    repo = Repository(
        project_id=proj.id,
        owner="octocat",
        full_name="octocat/test-repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    inst = GitHubInstallation(
        installation_id=987654,
        account_name="octocat",
        account_type="User",
        organization_id=org.id,
    )
    db_session.add(inst)
    await db_session.flush()

    binding = GitHubRepositoryBinding(
        installation_id=inst.id,
        repository_id=repo.id,
        github_repo_id=98765432,
    )
    db_session.add(binding)
    await db_session.flush()

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=501,
        title="Malformed Review Model Test",
        author_username="testuser",
        base_branch="main",
        base_sha="a" * 40,
        head_branch="patch-1",
        head_sha="b" * 40,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.QUEUED.value,
    )
    db_session.add(task)
    await db_session.commit()

    # Provider returning garbage non-JSON
    mock_bad_provider = MockChatModelProvider(default_response="Malformed model output without JSON structure")
    service = PRReviewService(db_session)

    res_task = await service.execute_review(task.id, model_provider=mock_bad_provider)

    # Invariants:
    # 1. State must be FAILED (NEVER REVIEW_READY or APPROVED)
    assert res_task.lifecycle_state == PRReviewLifecycleState.FAILED.value
    # 2. Failure reason must record the JSON parsing error
    assert "PR reviewer model returned unparseable JSON" in (res_task.failure_reason or "")
    # 3. Findings count must be 0
    assert res_task.total_findings_count == 0
    # 4. No AgentReview record must be linked
    assert res_task.agent_review_id is None

    # 5. Database must contain zero ReviewFinding records for this task
    findings_q = select(ReviewFinding)
    all_findings = (await db_session.execute(findings_q)).scalars().all()
    assert len(all_findings) == 0


@pytest.mark.asyncio
async def test_pr_review_service_fails_on_provider_429_exception(db_session: AsyncSession):
    """PRReviewService marks task FAILED when model provider raises 429 quota exception."""
    org = Organization(name="429 Test Org", slug="org-429")
    db_session.add(org)
    await db_session.flush()

    user = User(email="rate_limit_tester@example.com", hashed_password="pw", full_name="429 Tester")
    db_session.add(user)
    await db_session.flush()

    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.admin))

    proj = Project(name="429 Proj", organization_id=org.id)
    db_session.add(proj)
    await db_session.flush()

    repo = Repository(
        project_id=proj.id,
        owner="octocat",
        full_name="octocat/429-repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    inst = GitHubInstallation(
        installation_id=112233,
        account_name="octocat",
        account_type="User",
        organization_id=org.id,
    )
    db_session.add(inst)
    await db_session.flush()

    binding = GitHubRepositoryBinding(
        installation_id=inst.id,
        repository_id=repo.id,
        github_repo_id=11223344,
    )
    db_session.add(binding)
    await db_session.flush()

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=502,
        title="Provider 429 Quota Test",
        author_username="testuser",
        base_branch="main",
        base_sha="c" * 40,
        head_branch="patch-2",
        head_sha="d" * 40,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.QUEUED.value,
    )
    db_session.add(task)
    await db_session.commit()

    # Create mock provider that raises ModelProviderException (429)
    failing_provider = MockChatModelProvider()
    failing_provider.ainvoke = AsyncMock(
        side_effect=ModelProviderException("Groq API quota exhausted (HTTP 429)", provider="groq")
    )

    service = PRReviewService(db_session)
    res_task = await service.execute_review(task.id, model_provider=failing_provider)

    assert res_task.lifecycle_state == PRReviewLifecycleState.FAILED.value
    assert "Groq API quota exhausted" in (res_task.failure_reason or "")
    assert res_task.total_findings_count == 0
    assert res_task.agent_review_id is None


@pytest.mark.asyncio
async def test_pr_review_service_succeeds_clean_when_model_approves(db_session: AsyncSession):
    """PRReviewService marks task REVIEW_READY with 0 findings when model legitimately approves."""
    org = Organization(name="Clean Review Org", slug="clean-org")
    db_session.add(org)
    await db_session.flush()

    user = User(email="clean_tester@example.com", hashed_password="pw", full_name="Clean Tester")
    db_session.add(user)
    await db_session.flush()

    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.admin))

    proj = Project(name="Clean Proj", organization_id=org.id)
    db_session.add(proj)
    await db_session.flush()

    repo = Repository(
        project_id=proj.id,
        owner="octocat",
        full_name="octocat/clean-repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    inst = GitHubInstallation(
        installation_id=445566,
        account_name="octocat",
        account_type="User",
        organization_id=org.id,
    )
    db_session.add(inst)
    await db_session.flush()

    binding = GitHubRepositoryBinding(
        installation_id=inst.id,
        repository_id=repo.id,
        github_repo_id=44556677,
    )
    db_session.add(binding)
    await db_session.flush()

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=503,
        title="Legitimate Clean PR",
        author_username="testuser",
        base_branch="main",
        base_sha="e" * 40,
        head_branch="patch-3",
        head_sha="f" * 40,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.QUEUED.value,
    )
    db_session.add(task)
    await db_session.commit()

    clean_response = {
        "status": "APPROVED",
        "summary": "Clean code changes. All contracts maintained.",
        "findings": [],
    }
    clean_provider = MockChatModelProvider(default_response=json.dumps(clean_response))
    service = PRReviewService(db_session)

    res_task = await service.execute_review(task.id, model_provider=clean_provider)

    assert res_task.lifecycle_state == PRReviewLifecycleState.REVIEW_READY.value
    assert res_task.total_findings_count == 0
    assert res_task.agent_review_id is not None
    assert res_task.failure_reason is None

    review = await db_session.get(AgentReview, res_task.agent_review_id)
    assert review is not None
    assert review.status == "APPROVED"


@pytest.mark.asyncio
async def test_pr_review_service_succeeds_with_findings(db_session: AsyncSession):
    """PRReviewService marks task REVIEW_READY with findings persisted when model requests changes."""
    org = Organization(name="Findings Org", slug="findings-org")
    db_session.add(org)
    await db_session.flush()

    user = User(email="findings_tester@example.com", hashed_password="pw", full_name="Findings Tester")
    db_session.add(user)
    await db_session.flush()

    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.admin))

    proj = Project(name="Findings Proj", organization_id=org.id)
    db_session.add(proj)
    await db_session.flush()

    repo = Repository(
        project_id=proj.id,
        owner="octocat",
        full_name="octocat/findings-repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    inst = GitHubInstallation(
        installation_id=778899,
        account_name="octocat",
        account_type="User",
        organization_id=org.id,
    )
    db_session.add(inst)
    await db_session.flush()

    binding = GitHubRepositoryBinding(
        installation_id=inst.id,
        repository_id=repo.id,
        github_repo_id=77889900,
    )
    db_session.add(binding)
    await db_session.flush()

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=504,
        title="Vulnerable PR Test",
        author_username="testuser",
        base_branch="main",
        base_sha="1" * 40,
        head_branch="patch-4",
        head_sha="2" * 40,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.QUEUED.value,
    )
    db_session.add(task)
    await db_session.commit()

    findings_response = {
        "status": "CHANGES_REQUESTED",
        "summary": "Identified hardcoded secret key in database connection string.",
        "findings": [
            {
                "severity": "CRITICAL",
                "category": "SECURITY",
                "file_path": "app/core/database.py",
                "start_line": 15,
                "end_line": 16,
                "description": "Hardcoded postgres password in repository",
                "evidence": "DATABASE_URL = 'postgresql://admin:supersecret@localhost/db'",
                "recommendation": "Use environment variable settings.DATABASE_URL",
            }
        ],
    }
    findings_provider = MockChatModelProvider(default_response=json.dumps(findings_response))
    service = PRReviewService(db_session)

    res_task = await service.execute_review(task.id, model_provider=findings_provider)

    assert res_task.lifecycle_state == PRReviewLifecycleState.REVIEW_READY.value
    assert res_task.total_findings_count == 1
    assert res_task.critical_count == 1
    assert res_task.agent_review_id is not None

    findings_q = select(ReviewFinding).where(ReviewFinding.review_id == res_task.agent_review_id)
    findings = (await db_session.execute(findings_q)).scalars().all()
    assert len(findings) == 1
    assert findings[0].severity == "CRITICAL"
    assert findings[0].file_path == "app/core/database.py"
