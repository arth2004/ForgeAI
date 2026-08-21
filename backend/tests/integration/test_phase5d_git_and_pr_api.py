import datetime
import tempfile
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.git_tools import (
    CommitChangesTool,
    CreatePullRequestTool,
    PushBranchTool,
)
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


@pytest.fixture
async def git_test_context(db_session: AsyncSession, test_user: User):
    """Provisions organization, project, repository, session, and workspace initialized with a local git repo."""
    org = Organization(name="Forge Git Org", slug="forge-git-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(
        user_id=test_user.id,
        organization_id=org.id,
        role=Role.admin,
    )
    db_session.add(membership)

    project = Project(
        name="Git Integration Test Project",
        organization_id=org.id,
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        full_name="forge/git-repo",
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
    await db_session.flush()

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
        branch_id=branch.id,
    )
    db_session.add(session)
    await db_session.flush()

    # Create temporary directory for workspace
    tmp_ws_dir = tempfile.mkdtemp(prefix="forge_git_ws_")
    ws_path = Path(tmp_ws_dir)
    (ws_path / "app").mkdir(parents=True, exist_ok=True)
    auth_file = ws_path / "app" / "service.py"
    auth_file.write_text("def run():\n    return True\n", encoding="utf-8")

    workspace = AgentWorkspace(
        id=uuid.uuid4(),
        session_id=session.id,
        organization_id=org.id,
        project_id=project.id,
        repository_id=repo.id,
        branch_id=branch.id,
        user_id=test_user.id,
        status=WorkspaceStatus.ACTIVE.value,
        path=str(ws_path),
        base_commit_sha=branch.latest_commit_sha,
        expires_at=utc_now() + datetime.timedelta(hours=1),
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(org)
    await db_session.refresh(project)
    await db_session.refresh(repo)
    await db_session.refresh(session)
    await db_session.refresh(workspace)

    yield {
        "org": org,
        "project": project,
        "repo": repo,
        "session": session,
        "workspace": workspace,
        "ws_path": ws_path,
        "auth_file": auth_file,
    }


@pytest.mark.asyncio
async def test_create_branch_and_get_git_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    git_test_context: dict,
):
    """POST /workspaces/{id}/branch and GET /workspaces/{id}/git-status."""
    workspace = git_test_context["workspace"]

    # 1. Create branch
    branch_res = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/branch",
        json={"branch_name": "forge/feature-test-branch"},
        headers=auth_headers,
    )
    assert branch_res.status_code == 201, branch_res.text
    assert branch_res.json()["branch_name"] == "forge/feature-test-branch"

    # 2. Get git status
    status_res = await client.get(
        f"/api/v1/agent/workspaces/{workspace.id}/git-status",
        headers=auth_headers,
    )
    assert status_res.status_code == 200, status_res.text
    data = status_res.json()
    assert data["branch_name"] == "forge/feature-test-branch"
    assert data["workspace_id"] == str(workspace.id)


@pytest.mark.asyncio
async def test_commit_lifecycle_and_approval_gate(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    git_test_context: dict,
):
    """Full commit lifecycle: unapproved commit fails -> approve COMMIT gate -> commit succeeds."""
    workspace = git_test_context["workspace"]

    # 1. Attempt commit without approval -> 403 Forbidden
    unapproved_res = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/commit",
        json={"message": "feat(test): initial commit"},
        headers=auth_headers,
    )
    assert unapproved_res.status_code in (403, 409)

    # 2. Create and approve COMMIT gate
    approval = AgentApproval(
        id=uuid.uuid4(),
        session_id=workspace.session_id,
        workspace_id=workspace.id,
        user_id=test_user.id,
        approval_type=ApprovalType.COMMIT.value,
        status=ApprovalStatus.APPROVED.value,
        resolved_at=utc_now(),
    )
    db_session.add(approval)
    await db_session.commit()

    # 3. Commit changes -> 201 Created
    commit_res = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/commit",
        json={"message": "feat(auth): enable token verification"},
        headers=auth_headers,
    )
    assert commit_res.status_code == 201, commit_res.text
    data = commit_res.json()
    assert data["commit_sha"] is not None
    assert "feat(auth): enable token verification" in data["message"]


@pytest.mark.asyncio
async def test_push_lifecycle_and_approval_gate(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    git_test_context: dict,
):
    """Full push lifecycle: unapproved push fails -> approve PUSH gate -> push succeeds."""
    workspace = git_test_context["workspace"]

    # 1. Setup branch and commit
    commit_appr = AgentApproval(
        id=uuid.uuid4(),
        session_id=workspace.session_id,
        workspace_id=workspace.id,
        user_id=test_user.id,
        approval_type=ApprovalType.COMMIT.value,
        status=ApprovalStatus.APPROVED.value,
        resolved_at=utc_now(),
    )
    db_session.add(commit_appr)
    await db_session.commit()

    await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/commit",
        json={"message": "feat(auth): pre-push commit"},
        headers=auth_headers,
    )

    # 2. Attempt push without PUSH approval -> 403 / 409
    unapproved_push = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/push",
        headers=auth_headers,
    )
    assert unapproved_push.status_code in (403, 409)

    # 3. Create and approve PUSH gate
    push_appr = AgentApproval(
        id=uuid.uuid4(),
        session_id=workspace.session_id,
        workspace_id=workspace.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PUSH.value,
        status=ApprovalStatus.APPROVED.value,
        resolved_at=utc_now(),
    )
    db_session.add(push_appr)
    await db_session.commit()

    # 4. Push branch -> 200 OK
    push_res = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/push",
        headers=auth_headers,
    )
    assert push_res.status_code == 200, push_res.text
    data = push_res.json()
    assert data["remote_branch_name"] is not None


@pytest.mark.asyncio
async def test_pull_request_creation_and_approval_gate(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    git_test_context: dict,
):
    """Full PR lifecycle: unapproved PR fails -> approve PR_CREATE gate -> PR created."""
    workspace = git_test_context["workspace"]

    # 1. Setup committed state
    commit_appr = AgentApproval(
        id=uuid.uuid4(),
        session_id=workspace.session_id,
        workspace_id=workspace.id,
        user_id=test_user.id,
        approval_type=ApprovalType.COMMIT.value,
        status=ApprovalStatus.APPROVED.value,
        resolved_at=utc_now(),
    )
    db_session.add(commit_appr)
    await db_session.commit()

    await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/commit",
        json={"message": "feat(auth): PR readiness commit"},
        headers=auth_headers,
    )

    # 2. Attempt PR creation without PR_CREATE approval -> 403 / 409
    unapproved_pr = await client.post(
        f"/api/v1/agent/pulls/{workspace.id}/create",
        headers=auth_headers,
    )
    assert unapproved_pr.status_code in (403, 409)

    # 3. Create and approve PR_CREATE gate
    pr_appr = AgentApproval(
        id=uuid.uuid4(),
        session_id=workspace.session_id,
        workspace_id=workspace.id,
        user_id=test_user.id,
        approval_type=ApprovalType.PR_CREATE.value,
        status=ApprovalStatus.APPROVED.value,
        resolved_at=utc_now(),
    )
    db_session.add(pr_appr)
    await db_session.commit()

    # 4. Create PR -> 201 Created
    pr_res = await client.post(
        f"/api/v1/agent/pulls/{workspace.id}/create",
        json={"title": "feat(auth): automated PR", "body": "PR description."},
        headers=auth_headers,
    )
    assert pr_res.status_code == 201, pr_res.text
    data = pr_res.json()
    assert data["pr_id"] is not None
    assert data["title"] == "feat(auth): automated PR"
    assert data["status"] == "CREATED"

    # 5. GET PR details
    pr_id = data["pr_id"]
    get_pr = await client.get(f"/api/v1/agent/pulls/{pr_id}", headers=auth_headers)
    assert get_pr.status_code == 200
    assert get_pr.json()["pr_id"] == pr_id


@pytest.mark.asyncio
async def test_unauthorized_cross_user_git_mutation(
    client: AsyncClient,
    db_session: AsyncSession,
    git_test_context: dict,
):
    """User B cannot create branch, commit, push, or create PR on User A's workspace (403 Forbidden)."""
    workspace = git_test_context["workspace"]

    # Create User B
    user_b = User(
        email="unauthorized_git@external.dev",
        hashed_password=hash_password("EvilPass123!"),
        full_name="Attacker",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    b_token = create_access_token(str(user_b.id))
    b_headers = {"Authorization": f"Bearer {b_token}"}

    # User B tries branch creation
    res1 = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/branch",
        headers=b_headers,
    )
    assert res1.status_code == 403

    # User B tries commit
    res2 = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/commit",
        headers=b_headers,
    )
    assert res2.status_code == 403

    # User B tries push
    res3 = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/push",
        headers=b_headers,
    )
    assert res3.status_code == 403


@pytest.mark.asyncio
async def test_critical_security_git_tools_blocked_for_autonomous_llm(
    db_session: AsyncSession,
    test_user: User,
):
    """CRITICAL SECURITY TEST: Verifies LLM cannot commit, push, or create PR autonomously from tool calls."""
    commit_tool = CommitChangesTool()
    res1 = await commit_tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res1.success is False
    assert "APPROVAL_REQUIRED" in res1.error
    assert "commit_changes" in res1.error

    push_tool = PushBranchTool()
    res2 = await push_tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res2.success is False
    assert "APPROVAL_REQUIRED" in res2.error
    assert "push_branch" in res2.error

    pr_tool = CreatePullRequestTool()
    res3 = await pr_tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res3.success is False
    assert "APPROVAL_REQUIRED" in res3.error
    assert "create_pull_request" in res3.error
