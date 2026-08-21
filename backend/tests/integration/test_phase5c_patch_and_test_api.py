import datetime
import tempfile
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.patching.validator import compute_file_sha256
from app.agent.tools.patch_tools import ApplyPatchTool
from app.core.security import create_access_token, hash_password
from app.models.agent import (
    AgentSession,
    AgentWorkspace,
    WorkspaceStatus,
)
from app.models.auth import Membership, Organization, Role, User
from app.models.base import utc_now
from app.models.project import Project, Repository, RepositoryBranch
from app.services.sandbox.runner import SandboxExecutionResult, TestExecutionStatus


@pytest.fixture
async def patch_test_context(db_session: AsyncSession, test_user: User):
    """Provisions organization, project, repository, session, and workspace for Phase 5C tests."""
    org = Organization(name="Forge Patch Org", slug="forge-patch-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(
        user_id=test_user.id,
        organization_id=org.id,
        role=Role.admin,
    )
    db_session.add(membership)

    project = Project(
        name="Patching Test Project",
        organization_id=org.id,
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        full_name="forge/patch-repo",
        default_branch="main",
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="b1b2c3d4e5f6789012345678901234567890abcd",
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
    tmp_ws_dir = tempfile.mkdtemp(prefix="forge_test_ws_")
    ws_path = Path(tmp_ws_dir)
    (ws_path / "app").mkdir(parents=True, exist_ok=True)
    auth_file = ws_path / "app" / "service.py"
    auth_file.write_text("def run():\n    return False\n", encoding="utf-8")

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
async def test_propose_patch_api(
    client: AsyncClient,
    auth_headers: dict[str, str],
    patch_test_context: dict,
):
    """POST /api/v1/agent/patches/propose validates patch and generates pending DIFF approval gate."""
    workspace = patch_test_context["workspace"]
    session = patch_test_context["session"]
    auth_file = patch_test_context["auth_file"]
    old_hash = compute_file_sha256(auth_file.read_bytes())

    patch_payload = {
        "workspace_id": str(workspace.id),
        "session_id": str(session.id),
        "summary": "Fix authentication return value",
        "files": [
            {
                "file_path": "app/service.py",
                "operation": "MODIFY",
                "old_content_hash": old_hash,
                "hunks": [
                    {
                        "id": "h1",
                        "old_start": 1,
                        "old_lines": 2,
                        "new_start": 1,
                        "new_lines": 2,
                        "old_content": "def run():\n    return False\n",
                        "new_content": "def run():\n    return True\n",
                    }
                ],
                "reason": "Correct boolean return value in run()",
            }
        ],
    }

    res = await client.post(
        "/api/v1/agent/patches/propose",
        json=patch_payload,
        headers=auth_headers,
    )

    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "AWAITING_APPROVAL"
    assert data["diff_content"] is not None
    assert "+++ b/app/service.py" in data["diff_content"]
    assert data["approval_id"] is not None


@pytest.mark.asyncio
async def test_get_patch_and_diff_api(
    client: AsyncClient,
    auth_headers: dict[str, str],
    patch_test_context: dict,
):
    """GET /api/v1/agent/patches/{id} and /diff endpoints."""
    workspace = patch_test_context["workspace"]
    session = patch_test_context["session"]
    auth_file = patch_test_context["auth_file"]
    old_hash = compute_file_sha256(auth_file.read_bytes())

    # Propose patch
    propose_res = await client.post(
        "/api/v1/agent/patches/propose",
        json={
            "workspace_id": str(workspace.id),
            "session_id": str(session.id),
            "summary": "Update service",
            "files": [
                {
                    "file_path": "app/service.py",
                    "operation": "MODIFY",
                    "old_content_hash": old_hash,
                    "hunks": [
                        {
                            "id": "h1",
                            "old_start": 1,
                            "old_lines": 2,
                            "new_start": 1,
                            "new_lines": 2,
                            "old_content": "def run():\n    return False\n",
                            "new_content": "def run():\n    return True\n",
                        }
                    ],
                }
            ],
        },
        headers=auth_headers,
    )
    patch_id = propose_res.json()["patch_id"]

    # 1. GET patch details
    get_res = await client.get(f"/api/v1/agent/patches/{patch_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["patch_id"] == patch_id

    # 2. GET patch diff
    diff_res = await client.get(f"/api/v1/agent/patches/{patch_id}/diff", headers=auth_headers)
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["files_changed"] == 1
    assert diff_data["lines_added"] > 0
    assert "+++ b/app/service.py" in diff_data["unified_diff"]


@pytest.mark.asyncio
async def test_approve_reject_and_apply_lifecycle(
    client: AsyncClient,
    auth_headers: dict[str, str],
    patch_test_context: dict,
):
    """Full lifecycle: propose -> unapproved apply rejected -> approve -> apply succeeds -> mutation verified."""
    workspace = patch_test_context["workspace"]
    session = patch_test_context["session"]
    auth_file = patch_test_context["auth_file"]
    old_hash = compute_file_sha256(auth_file.read_bytes())

    # 1. Propose patch
    propose_res = await client.post(
        "/api/v1/agent/patches/propose",
        json={
            "workspace_id": str(workspace.id),
            "session_id": str(session.id),
            "summary": "Fix boolean return",
            "files": [
                {
                    "file_path": "app/service.py",
                    "operation": "MODIFY",
                    "old_content_hash": old_hash,
                    "hunks": [
                        {
                            "id": "h1",
                            "old_start": 1,
                            "old_lines": 2,
                            "new_start": 1,
                            "new_lines": 2,
                            "old_content": "def run():\n    return False\n",
                            "new_content": "def run():\n    return True\n",
                        }
                    ],
                }
            ],
        },
        headers=auth_headers,
    )
    patch_id = propose_res.json()["patch_id"]

    # 2. Attempt apply WITHOUT approval -> 409 Conflict
    unapproved_apply = await client.post(f"/api/v1/agent/patches/{patch_id}/apply", headers=auth_headers)
    assert unapproved_apply.status_code == 409

    # 3. Approve patch
    approve_res = await client.post(
        f"/api/v1/agent/patches/{patch_id}/approve",
        json={"reason": "Diff looks accurate."},
        headers=auth_headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # 4. Apply patch -> 200 OK
    apply_res = await client.post(f"/api/v1/agent/patches/{patch_id}/apply", headers=auth_headers)
    assert apply_res.status_code == 200
    assert apply_res.json()["status"] == "APPLIED"
    assert "app/service.py" in apply_res.json()["files_modified"]

    # Verify physical file modification
    assert "return True" in auth_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_unauthorized_cross_user_patch_approval(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    patch_test_context: dict,
):
    """User B cannot approve or apply User A's patch (403 Forbidden)."""
    workspace = patch_test_context["workspace"]
    session = patch_test_context["session"]
    auth_file = patch_test_context["auth_file"]
    old_hash = compute_file_sha256(auth_file.read_bytes())

    # User A proposes patch
    propose_res = await client.post(
        "/api/v1/agent/patches/propose",
        json={
            "workspace_id": str(workspace.id),
            "session_id": str(session.id),
            "summary": "User A Patch",
            "files": [
                {
                    "file_path": "app/service.py",
                    "operation": "MODIFY",
                    "old_content_hash": old_hash,
                    "hunks": [
                        {
                            "id": "h1",
                            "old_start": 1,
                            "old_lines": 2,
                            "new_start": 1,
                            "new_lines": 2,
                            "old_content": "def run():\n    return False\n",
                            "new_content": "def run():\n    return True\n",
                        }
                    ],
                }
            ],
        },
        headers=auth_headers,
    )
    patch_id = propose_res.json()["patch_id"]

    # Create User B
    user_b = User(
        email="unauthorized@external.dev",
        hashed_password=hash_password("EvilPassword123!"),
        full_name="Attacker",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    b_token = create_access_token(str(user_b.id))
    b_headers = {"Authorization": f"Bearer {b_token}"}

    # User B tries to view patch
    get_res = await client.get(f"/api/v1/agent/patches/{patch_id}", headers=b_headers)
    assert get_res.status_code == 403

    # User B tries to approve patch
    appr_res = await client.post(f"/api/v1/agent/patches/{patch_id}/approve", headers=b_headers)
    assert appr_res.status_code == 403

    # User B tries to apply patch
    apply_res = await client.post(f"/api/v1/agent/patches/{patch_id}/apply", headers=b_headers)
    assert apply_res.status_code == 403


@pytest.mark.asyncio
async def test_sandboxed_test_execution_api(
    client: AsyncClient,
    auth_headers: dict[str, str],
    patch_test_context: dict,
    monkeypatch,
):
    """POST /api/v1/agent/workspaces/{workspace_id}/tests executes test runner inside sandbox."""
    workspace = patch_test_context["workspace"]

    async def mock_fake_run(self, workspace_path, test_command):
        return SandboxExecutionResult(
            status=TestExecutionStatus.PASSED,
            exit_code=0,
            stdout="collected 3 items\ntest_service.py ... [100%]\n3 passed in 0.12s",
            stderr="",
            duration_ms=120,
        )

    from app.services.sandbox.runner import SandboxRunner
    monkeypatch.setattr(SandboxRunner, "run_test", mock_fake_run)


    res = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/tests",
        json={
            "test_command": {
                "runner": "pytest",
                "arguments": ["tests/test_service.py"],
                "timeout_seconds": 60,
            }
        },
        headers=auth_headers,
    )

    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "PASSED"
    assert data["exit_code"] == 0
    assert "3 passed" in data["stdout"]

    test_id = data["test_id"]
    get_res = await client.get(f"/api/v1/agent/tests/{test_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["test_id"] == test_id


@pytest.mark.asyncio
async def test_critical_security_apply_patch_tool_blocked(db_session: AsyncSession, test_user: User):
    """CRITICAL SECURITY TEST: Verifies LLM cannot apply patch autonomously from tool call alone."""
    tool = ApplyPatchTool()
    result = await tool.aexecute(
        db=db_session,
        user_id=test_user.id,
        patch_id=uuid.uuid4(),
    )
    assert result.success is False
    assert "APPROVAL_REQUIRED" in result.error
    assert "POST /api/v1/agent/patches/{patch_id}/apply" in result.error
