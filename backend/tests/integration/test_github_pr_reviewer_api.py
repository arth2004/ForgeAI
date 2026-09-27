"""Integration tests for GitHub Webhook Receiver and PR Reviewer APIs."""

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import MockChatModelProvider
from app.core.config import settings
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


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
async def github_fixture(db_session: AsyncSession, test_user: User):
    """Sets up an organization, project, repository, GitHub App installation and repository binding."""
    org = Organization(name="GitHub Test Org", slug="github-test-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    project = Project(
        organization_id=org.id, name="GitHub Test Project", description="PR Review tests"
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        github_repo_id=12345678,
        owner="test-org",
        full_name="test-org/forge-repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    installation = GitHubInstallation(
        organization_id=org.id,
        installation_id=999888,
        account_name="test-org",
        account_type="Organization",
    )
    db_session.add(installation)
    await db_session.flush()

    binding = GitHubRepositoryBinding(
        installation_id=installation.id,
        repository_id=repo.id,
        github_repo_id=12345678,
        is_active=True,
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(installation)
    await db_session.refresh(binding)
    await db_session.refresh(repo)
    await db_session.refresh(project)

    return {
        "installation": installation,
        "binding": binding,
        "repo": repo,
        "project": project,
    }


@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(client: AsyncClient):
    payload = {"action": "opened"}
    response = await client.post(
        "/api/v1/github/webhooks",
        json=payload,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(client: AsyncClient):
    payload = json.dumps({"action": "opened"}).encode("utf-8")
    response = await client.post(
        "/api/v1/github/webhooks",
        content=payload,
        headers={
            "X-Hub-Signature-256": "sha256=badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbad",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_pr_opened_accepted(
    client: AsyncClient,
    github_fixture: dict,
):
    delivery_id = str(uuid.uuid4())
    payload_data = {
        "action": "opened",
        "installation": {"id": 999888},
        "repository": {"id": 12345678, "full_name": "test-org/forge-repo"},
        "pull_request": {
            "number": 101,
            "title": "Fix token bucket float precision",
            "body": "Resolves concurrency race in rate limiter.",
            "user": {"login": "octocat"},
            "base": {"ref": "main", "sha": "base1234567890abcdef1234567890abcdef12"},
            "head": {"ref": "fix-tokens", "sha": "head1234567890abcdef1234567890abcdef12"},
            "draft": False,
            "changed_files": 2,
        },
    }
    raw_payload = json.dumps(payload_data).encode("utf-8")
    sig = _sign(raw_payload, settings.GITHUB_WEBHOOK_SECRET)

    response = await client.post(
        "/api/v1/github/webhooks",
        content=raw_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["delivery_id"] == delivery_id
    assert data["task_id"] is not None
    assert data["snapshot_id"] is not None


@pytest.mark.asyncio
async def test_webhook_deduplication(
    client: AsyncClient,
    github_fixture: dict,
):
    delivery_id = str(uuid.uuid4())
    payload_data = {
        "action": "opened",
        "installation": {"id": 999888},
        "repository": {"id": 12345678},
        "pull_request": {
            "number": 102,
            "title": "PR Duplicate Test",
            "base": {"ref": "main", "sha": "b" * 40},
            "head": {"ref": "feat", "sha": "h" * 40},
        },
    }
    raw_payload = json.dumps(payload_data).encode("utf-8")
    sig = _sign(raw_payload, settings.GITHUB_WEBHOOK_SECRET)

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": "pull_request",
    }

    # First delivery
    r1 = await client.post("/api/v1/github/webhooks", content=raw_payload, headers=headers)
    assert r1.status_code == 202

    # Second duplicate delivery
    r2 = await client.post("/api/v1/github/webhooks", content=raw_payload, headers=headers)
    assert r2.status_code == 200
    assert "Duplicate webhook delivery ignored" in r2.json()["message"]


@pytest.mark.asyncio
async def test_pr_review_service_execution_flow(
    db_session: AsyncSession,
    github_fixture: dict,
):
    binding = github_fixture["binding"]

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=201,
        title="Audit rate limiter",
        body_summary="Auditing concurrency",
        author_username="developer",
        base_branch="main",
        base_sha="1111111111111111111111111111111111111111",
        head_branch="patch-1",
        head_sha="2222222222222222222222222222222222222222",
        changed_files_count=1,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.QUEUED.value,
    )
    db_session.add(task)
    await db_session.commit()

    # Execute review with mock model
    mock_model = MockChatModelProvider(
        default_response=json.dumps({
            "status": "CHANGES_REQUESTED",
            "summary": "Detected 1 critical race condition in rate_limiter.py",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "category": "SECURITY",
                    "file_path": "app/core/rate_limiter.py",
                    "start_line": 15,
                    "end_line": 20,
                    "description": "Float rounding causes negative token balance under concurrency",
                    "evidence": "tokens = tokens - float(requested)",
                    "recommendation": "Use Decimal arithmetic",
                }
            ],
        })
    )

    review_service = PRReviewService(db_session)
    completed_task = await review_service.execute_review(task.id, model_provider=mock_model)

    assert completed_task.lifecycle_state == PRReviewLifecycleState.REVIEW_READY.value
    assert completed_task.total_findings_count == 1
    assert completed_task.critical_count == 1
    assert completed_task.agent_review_id is not None


@pytest.mark.asyncio
async def test_get_pr_review_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    github_fixture: dict,
):
    binding = github_fixture["binding"]
    repo = github_fixture["repo"]

    snapshot = PullRequestSnapshot(
        repository_binding_id=binding.id,
        pr_number=301,
        title="Fix API Auth",
        body_summary="Auth check",
        author_username="octocat",
        base_branch="main",
        base_sha="a" * 40,
        head_branch="auth-fix",
        head_sha="b" * 40,
    )
    db_session.add(snapshot)
    await db_session.flush()

    task = PullRequestReviewTask(
        snapshot_id=snapshot.id,
        lifecycle_state=PRReviewLifecycleState.REVIEW_READY.value,
        total_findings_count=0,
    )
    db_session.add(task)
    await db_session.commit()

    # Test GET /pulls/{snapshot_id}
    res = await client.get(f"/api/v1/github/pulls/{snapshot.id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["snapshot"]["pr_number"] == 301
    assert data["lifecycle_state"] == "REVIEW_READY"

    # Test GET /repositories/{repo_id}/pulls
    list_res = await client.get(f"/api/v1/github/repositories/{repo.id}/pulls", headers=auth_headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1
