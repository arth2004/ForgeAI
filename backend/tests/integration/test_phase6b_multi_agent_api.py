"""Integration and Critical Security tests for Phase 6B Multi-Agent Engineering Runtime."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import AgentExecutionException
from app.agent.models import MockChatModelProvider
from app.agent.multi_agent.coder import CoderAgent
from app.agent.multi_agent.orchestrator import EngineeringOrchestrator
from app.agent.multi_agent.planner import PlannerAgent
from app.agent.multi_agent.reviewer import ReviewerAgent
from app.agent.multi_agent.state import create_initial_multi_agent_state
from app.agent.multi_agent.tester import TesterAgent
from app.agent.multi_agent.types import TaskLifecycleState
from app.models.agent import AgentSession
from app.models.auth import Organization, User
from app.models.project import Project, Repository


@pytest.fixture
async def setup_multi_agent_env(db_session: AsyncSession):
    """Sets up a complete organization, user, project, repository, and session for multi-agent testing."""
    org = Organization(name="MultiAgent Org", slug=f"org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    from app.models.auth import Membership, Role

    user = User(
        email=f"engineer-{uuid.uuid4().hex[:6]}@forge.ai",
        hashed_password="hashedpassword",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership_1 = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=Role.admin,
    )
    db_session.add(membership_1)

    other_org = Organization(name="Other Tenant Org", slug=f"other-{uuid.uuid4().hex[:6]}")
    db_session.add(other_org)
    await db_session.flush()

    other_user = User(
        email=f"other-{uuid.uuid4().hex[:6]}@other.ai",
        hashed_password="hashedpassword",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    membership_2 = Membership(
        user_id=other_user.id,
        organization_id=other_org.id,
        role=Role.admin,
    )
    db_session.add(membership_2)


    project = Project(
        name="MultiAgent Project",
        organization_id=org.id,
    )
    db_session.add(project)
    await db_session.flush()


    repo = Repository(
        project_id=project.id,
        github_repo_id=1234567,
        full_name="forge-ai/agent-repo",
        owner="forge-ai",
        default_branch="main",
    )
    db_session.add(repo)
    await db_session.flush()


    session = AgentSession(
        user_id=user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.commit()

    return {
        "org": org,
        "user": user,
        "other_org": other_org,
        "other_user": other_user,
        "project": project,
        "repo": repo,
        "session": session,
    }


@pytest.mark.asyncio
async def test_create_and_get_agent_task_api(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_multi_agent_env: dict,
):
    """Verifies POST /api/v1/agent/tasks and GET /api/v1/agent/tasks/{id} API endpoints."""
    from app.core.security import create_access_token

    env = setup_multi_agent_env
    user = env["user"]
    token = create_access_token(subject=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create multi-agent task
    req_data = {
        "prompt": "Implement distributed rate limiter across FastAPI endpoints",
        "project_id": str(env["project"].id),
        "repository_id": str(env["repo"].id),
        "session_id": str(env["session"].id),
        "title": "Rate Limiter Task",
    }

    res = await client.post("/api/v1/agent/tasks", json=req_data, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()
    task_id = data["id"]
    assert data["title"] == "Rate Limiter Task"
    assert data["lifecycle_state"] == "TASK_CREATED"
    assert data["active_agent"] == "SUPERVISOR"

    # 2. Get task details
    get_res = await client.get(f"/api/v1/agent/tasks/{task_id}", headers=headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == task_id
    assert get_data["prompt"] == req_data["prompt"]


@pytest.mark.asyncio
async def test_cancel_agent_task_api(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_multi_agent_env: dict,
):
    """Verifies POST /api/v1/agent/tasks/{id}/cancel transitions task to CANCELLED state."""
    from app.core.security import create_access_token

    env = setup_multi_agent_env
    user = env["user"]
    token = create_access_token(subject=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    req_data = {
        "prompt": "Task to cancel",
        "project_id": str(env["project"].id),
        "repository_id": str(env["repo"].id),
    }
    res = await client.post("/api/v1/agent/tasks", json=req_data, headers=headers)
    task_id = res.json()["id"]

    cancel_res = await client.post(f"/api/v1/agent/tasks/{task_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["lifecycle_state"] == "CANCELLED"
    assert "Cancelled" in cancel_data["failure_reason"]


# =========================================================================
# CRITICAL SECURITY TESTS (1 - 12)
# =========================================================================


@pytest.mark.asyncio
async def test_critical_security_1_planner_cannot_apply_patch():
    """Security Invariant 1: PlannerAgent cannot execute apply_patch."""
    planner = PlannerAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        planner.validate_tool_access("apply_patch")


@pytest.mark.asyncio
async def test_critical_security_2_coder_cannot_commit_without_approval():
    """Security Invariant 2: CoderAgent cannot execute git_commit without human approval."""
    coder = CoderAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("git_commit")


@pytest.mark.asyncio
async def test_critical_security_3_coder_cannot_push_without_approval():
    """Security Invariant 3: CoderAgent cannot execute git_push without human approval."""
    coder = CoderAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("git_push")


@pytest.mark.asyncio
async def test_critical_security_4_reviewer_cannot_mutate_workspace():
    """Security Invariant 4: ReviewerAgent has zero workspace mutation authority."""
    reviewer = ReviewerAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        reviewer.validate_tool_access("apply_patch")
    with pytest.raises(AgentExecutionException):
        reviewer.validate_tool_access("propose_patch")


@pytest.mark.asyncio
async def test_critical_security_5_tester_cannot_execute_arbitrary_shell():
    """Security Invariant 5: TesterAgent cannot execute unallowlisted shell commands."""
    tester = TesterAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        tester.validate_tool_access("bash")
    with pytest.raises(AgentExecutionException):
        tester.validate_tool_access("sh")


@pytest.mark.asyncio
async def test_critical_security_6_agent_cannot_bypass_gate_1_plan():
    """Security Invariant 6: Orchestrator halts at Gate 1 until PLAN approval is granted."""
    mock_provider = MockChatModelProvider(
        default_response='{"summary": "Plan", "problem_statement": "Problem", "approach": "Approach", "affected_files": [], "new_files": [], "deleted_files": [], "test_strategy": "pytest", "risks": [], "sources": []}'
    )
    orchestrator = EngineeringOrchestrator(
        planner_provider=mock_provider,
        coder_provider=mock_provider,
        tester_provider=mock_provider,
        reviewer_provider=mock_provider,
    )

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Gate 1 test",
    )

    # Initial run -> pauses at Gate 1
    result = await orchestrator.ainvoke(state)
    assert result["lifecycle_state"] == TaskLifecycleState.PLAN_READY.value
    assert result["approval_status"]["PLAN"] == "PENDING"

    # Subsequent run without approval must NOT advance to coder
    result_repeat = await orchestrator.ainvoke(result)
    assert result_repeat["lifecycle_state"] == TaskLifecycleState.PLAN_READY.value


@pytest.mark.asyncio
async def test_critical_security_7_agent_cannot_bypass_gate_2_diff():
    """Security Invariant 7: Orchestrator halts at Gate 2 until DIFF approval is granted."""
    mock_provider = MockChatModelProvider()
    orchestrator = EngineeringOrchestrator(
        planner_provider=mock_provider,
        coder_provider=mock_provider,
        tester_provider=mock_provider,
        reviewer_provider=mock_provider,
    )

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Gate 2 test",
    )
    state["approval_status"]["PLAN"] = "APPROVED"
    state["lifecycle_state"] = TaskLifecycleState.WORKSPACE_READY.value

    # Advances to Coder -> pauses at Gate 2 (PATCH_READY)
    result = await orchestrator.ainvoke(state)
    assert result["lifecycle_state"] == TaskLifecycleState.PATCH_READY.value
    assert result["approval_status"]["DIFF"] == "PENDING"

    # Subsequent run without DIFF approval must NOT advance to tester
    result_repeat = await orchestrator.ainvoke(result)
    assert result_repeat["lifecycle_state"] == TaskLifecycleState.PATCH_READY.value


@pytest.mark.asyncio
async def test_critical_security_8_agent_cannot_bypass_gate_3_commit():
    """Security Invariant 8: Agent cannot commit to git without human approval."""
    coder = CoderAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("git_commit")


@pytest.mark.asyncio
async def test_critical_security_9_agent_cannot_bypass_gate_4_push():
    """Security Invariant 9: Agent cannot push to remote without human approval."""
    coder = CoderAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("git_push")


@pytest.mark.asyncio
async def test_critical_security_10_agent_cannot_bypass_gate_5_pr():
    """Security Invariant 10: Agent cannot create pull requests without human approval."""
    coder = CoderAgent(model_provider=MockChatModelProvider())
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("create_pull_request")


@pytest.mark.asyncio
async def test_critical_security_11_cross_tenant_task_access_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_multi_agent_env: dict,
):
    """Security Invariant 11: Cross-tenant task retrieval strictly returns 403."""
    from app.core.security import create_access_token

    env = setup_multi_agent_env
    user_tenant_a = env["user"]
    user_tenant_b = env["other_user"]

    token_a = create_access_token(subject=str(user_tenant_a.id))
    token_b = create_access_token(subject=str(user_tenant_b.id))

    # 1. User A creates task in Tenant A
    create_res = await client.post(
        "/api/v1/agent/tasks",
        json={
            "prompt": "Tenant A Secret Task",
            "project_id": str(env["project"].id),
            "repository_id": str(env["repo"].id),
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    task_id = create_res.json()["id"]

    # 2. User B (Tenant B) attempts to read Tenant A's task -> 403 Forbidden
    res_b = await client.get(
        f"/api/v1/agent/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 403


@pytest.mark.asyncio
async def test_critical_security_12_cross_session_task_access_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_multi_agent_env: dict,
):
    """Security Invariant 12: User cannot link another user's session during task creation."""
    from app.core.security import create_access_token

    env = setup_multi_agent_env
    user_b = env["other_user"]

    token_b = create_access_token(subject=str(user_b.id))


    # User B attempts to create a task hijacking User A's session -> 403 Forbidden
    res = await client.post(
        "/api/v1/agent/tasks",
        json={
            "prompt": "Session Hijack Attempt",
            "project_id": str(env["project"].id),
            "repository_id": str(env["repo"].id),
            "session_id": str(env["session"].id),
        },
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code in [403, 404]
