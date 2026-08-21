import datetime
import json
import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_agent_graph
from app.agent.models import MockChatModelProvider
from app.core.security import create_access_token, hash_password
from app.models.agent import (
    AgentApproval,
    AgentSession,
    AgentWorkspace,
    ApprovalStatus,
    ApprovalType,
    WorkspaceStatus,
)
from app.models.auth import Membership, Organization, Role, User
from app.models.base import utc_now
from app.models.project import Project, Repository, RepositoryBranch


def _make_graph_builder(provider: MockChatModelProvider):
    def _builder(**kwargs):
        kwargs.pop("model_provider", None)
        return build_agent_graph(model_provider=provider, **kwargs)

    return _builder


@pytest.fixture
async def planning_test_context(db_session: AsyncSession, test_user: User):
    """Provisions a test organization, project, repository, and branch for Phase 5B tests."""
    org = Organization(name="Forge Planning Org", slug="forge-planning-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(
        user_id=test_user.id,
        organization_id=org.id,
        role=Role.admin,
    )
    db_session.add(membership)

    project = Project(
        name="Planning Test Project",
        organization_id=org.id,
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        full_name="forge/planning-repo",
        default_branch="main",
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="a1b2c3d4e5f6789012345678901234567890abcd",
        is_protected=True,
    )
    db_session.add(branch)
    await db_session.commit()
    await db_session.refresh(org)
    await db_session.refresh(project)
    await db_session.refresh(repo)
    await db_session.refresh(branch)

    return {
        "org": org,
        "project": project,
        "repo": repo,
        "branch": branch,
    }


@pytest.mark.asyncio
async def test_generate_plan_api(
    client: AsyncClient,
    auth_headers: dict[str, str],
    planning_test_context: dict,
):
    """POST /api/v1/agent/plan generates an implementation plan and pending Gate 1 approval."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]
    branch = planning_test_context["branch"]

    plan_json = json.dumps(
        {
            "summary": "Add structured JWT claims validation to auth module",
            "problem_statement": "JWT tokens lack custom claims decoding.",
            "approach": "Enhance security service with claims decoder.",
            "affected_files": [
                {
                    "file_path": "app/core/security.py",
                    "change_type": "MODIFY",
                    "reason": "Add custom claims parsing",
                    "symbols": ["create_access_token"],
                }
            ],
            "new_files": [],
            "deleted_files": [],
            "symbols": ["create_access_token"],
            "test_strategy": "Run test_security.py",
            "risks": ["Token expiration handling"],
        }
    )
    mock_provider = MockChatModelProvider(responses=[AIMessage(content=f"```json\n{plan_json}\n```")])

    with patch("app.services.planning_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)
        res = await client.post(
            "/api/v1/agent/plan",
            json={
                "message": "Add structured JWT claims validation to auth module",
                "project_id": str(project.id),
                "repository_id": str(repo.id),
                "branch_id": str(branch.id),
            },
            headers=auth_headers,
        )

    assert res.status_code == 200, res.text
    data = res.json()
    assert "plan" in data
    assert "approval_id" in data
    assert data["approval_status"] == "PENDING"
    assert data["project_id"] == str(project.id)
    assert data["repository_id"] == str(repo.id)
    assert data["plan"]["summary"] != ""


@pytest.mark.asyncio
async def test_plan_stream_generation_sse(
    client: AsyncClient,
    auth_headers: dict[str, str],
    planning_test_context: dict,
):
    """POST /api/v1/agent/plan/stream streams investigation and emits plan + approval events."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]
    branch = planning_test_context["branch"]

    plan_json = json.dumps(
        {
            "summary": "Refactor database connection pool timeout",
            "problem_statement": "Pool timeout needs tuning under high concurrency.",
            "approach": "Adjust pool size parameters in database config.",
            "affected_files": [
                {
                    "file_path": "app/core/database.py",
                    "change_type": "MODIFY",
                    "reason": "Configure connection pool size and timeout.",
                    "symbols": ["AsyncSessionLocal"],
                }
            ],
            "new_files": [],
            "deleted_files": [],
            "symbols": ["AsyncSessionLocal"],
            "test_strategy": "Run database integration tests.",
            "risks": ["Database max connection ceiling"],
        }
    )
    mock_provider = MockChatModelProvider(responses=[AIMessage(content=f"```json\n{plan_json}\n```")])

    with patch("app.services.planning_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)
        res = await client.post(
            "/api/v1/agent/plan/stream",
            json={
                "message": "Refactor database connection pool timeout",
                "project_id": str(project.id),
                "repository_id": str(repo.id),
                "branch_id": str(branch.id),
            },
            headers=auth_headers,
        )

    assert res.status_code == 200
    content = res.text
    assert "event: session.created" in content
    assert "event: agent.started" in content
    assert "event: agent.plan.created" in content
    assert "event: agent.approval.required" in content



@pytest.mark.asyncio
async def test_approve_and_reject_plan_lifecycle(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    planning_test_context: dict,
):
    """Approve and Reject endpoints transition approval gate status properly."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.flush()

    # 1. Test Approval
    appr1 = AgentApproval(
        session_id=session.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PLAN.value,
        status=ApprovalStatus.PENDING.value,
        plan_payload={"summary": "Test Plan 1"},
    )
    db_session.add(appr1)
    await db_session.commit()

    approve_res = await client.post(
        f"/api/v1/agent/approvals/{appr1.id}/approve",
        json={"reason": "Plan looks solid."},
        headers=auth_headers,
    )
    assert approve_res.status_code == 200
    data1 = approve_res.json()
    assert data1["status"] == "APPROVED"
    assert data1["resolved_at"] is not None

    # Cannot re-approve an already approved plan (Conflict)
    conflict_res = await client.post(
        f"/api/v1/agent/approvals/{appr1.id}/approve",
        headers=auth_headers,
    )
    assert conflict_res.status_code == 409

    # 2. Test Rejection
    appr2 = AgentApproval(
        session_id=session.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PLAN.value,
        status=ApprovalStatus.PENDING.value,
        plan_payload={"summary": "Test Plan 2"},
    )
    db_session.add(appr2)
    await db_session.commit()

    reject_res = await client.post(
        f"/api/v1/agent/approvals/{appr2.id}/reject",
        json={"reason": "Too risky."},
        headers=auth_headers,
    )
    assert reject_res.status_code == 200
    data2 = reject_res.json()
    assert data2["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_unauthorized_cross_user_plan_approval(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    planning_test_context: dict,
):
    """User B cannot approve or view User A's plan approval."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.flush()

    approval = AgentApproval(
        session_id=session.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PLAN.value,
        status=ApprovalStatus.PENDING.value,
        plan_payload={"summary": "User A Plan"},
    )
    db_session.add(approval)
    await db_session.commit()

    # Create User B
    user_b = User(
        email="attacker@external.dev",
        hashed_password=hash_password("EvilPass123!"),
        full_name="Attacker",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    b_token = create_access_token(str(user_b.id))
    b_headers = {"Authorization": f"Bearer {b_token}"}

    # User B tries to view approval
    get_res = await client.get(
        f"/api/v1/agent/approvals/{approval.id}",
        headers=b_headers,
    )
    assert get_res.status_code == 403

    # User B tries to approve
    post_res = await client.post(
        f"/api/v1/agent/approvals/{approval.id}/approve",
        headers=b_headers,
    )
    assert post_res.status_code == 403


@pytest.mark.asyncio
async def test_workspace_creation_with_approved_plan(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    planning_test_context: dict,
):
    """Approved plan enables isolated workspace creation with base commit SHA and TTL."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]
    branch = planning_test_context["branch"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
        branch_id=branch.id,
    )
    db_session.add(session)
    await db_session.flush()

    # 1. Unapproved plan rejected
    pending_appr = AgentApproval(
        session_id=session.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PLAN.value,
        status=ApprovalStatus.PENDING.value,
        plan_payload={"summary": "Unapproved Plan"},
    )
    db_session.add(pending_appr)
    await db_session.commit()

    fail_res = await client.post(
        "/api/v1/agent/workspaces",
        json={"session_id": str(session.id), "approval_id": str(pending_appr.id)},
        headers=auth_headers,
    )
    assert fail_res.status_code == 409

    # 2. Approve plan
    pending_appr.status = ApprovalStatus.APPROVED.value
    await db_session.commit()

    # 3. Create workspace
    create_res = await client.post(
        "/api/v1/agent/workspaces",
        json={"session_id": str(session.id), "approval_id": str(pending_appr.id)},
        headers=auth_headers,
    )
    assert create_res.status_code == 201, create_res.text
    ws_data = create_res.json()
    assert ws_data["status"] == "PREPARED"
    assert ws_data["base_commit_sha"] == branch.latest_commit_sha
    assert ws_data["path"] != ""
    assert os.path.exists(ws_data["path"])

    # 4. Duplicate workspace concurrency protection
    dup_res = await client.post(
        "/api/v1/agent/workspaces",
        json={"session_id": str(session.id), "approval_id": str(pending_appr.id)},
        headers=auth_headers,
    )
    assert dup_res.status_code == 409


@pytest.mark.asyncio
async def test_workspace_get_and_delete_idempotency(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    planning_test_context: dict,
):
    """GET and DELETE workspace endpoints with idempotency verification."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.flush()

    approval = AgentApproval(
        session_id=session.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PLAN.value,
        status=ApprovalStatus.APPROVED.value,
        plan_payload={"summary": "Approved Plan"},
    )
    db_session.add(approval)
    await db_session.commit()

    create_res = await client.post(
        "/api/v1/agent/workspaces",
        json={"session_id": str(session.id), "approval_id": str(approval.id)},
        headers=auth_headers,
    )
    ws_id = create_res.json()["workspace_id"]
    ws_path = create_res.json()["path"]

    # GET workspace
    get_res = await client.get(
        f"/api/v1/agent/workspaces/{ws_id}",
        headers=auth_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["workspace_id"] == ws_id

    # DELETE workspace (first call)
    del_res1 = await client.delete(
        f"/api/v1/agent/workspaces/{ws_id}",
        headers=auth_headers,
    )
    assert del_res1.status_code == 200
    assert del_res1.json()["status"] == "DESTROYED"
    assert not os.path.exists(ws_path)

    # DELETE workspace (idempotent second call)
    del_res2 = await client.delete(
        f"/api/v1/agent/workspaces/{ws_id}",
        headers=auth_headers,
    )
    assert del_res2.status_code == 200
    assert del_res2.json()["status"] == "DESTROYED"


@pytest.mark.asyncio
async def test_expired_workspace_access(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    planning_test_context: dict,
):
    """Expired workspace returns HTTP 410 controlled error."""
    project = planning_test_context["project"]
    repo = planning_test_context["repo"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.flush()

    past_time = utc_now() - datetime.timedelta(hours=2)
    workspace = AgentWorkspace(
        session_id=session.id,
        organization_id=planning_test_context["org"].id,
        project_id=project.id,
        repository_id=repo.id,
        user_id=test_user.id,
        status=WorkspaceStatus.ACTIVE.value,
        path="/tmp/forge_workspaces/expired",
        base_commit_sha="1111111111111111111111111111111111111111",
        expires_at=past_time,
    )
    db_session.add(workspace)
    await db_session.commit()

    res = await client.get(
        f"/api/v1/agent/workspaces/{workspace.id}",
        headers=auth_headers,
    )
    assert res.status_code == 410
    err_text = (res.json().get("message") or res.json().get("error") or "").lower()
    assert "expired" in err_text

