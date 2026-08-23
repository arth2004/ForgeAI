"""Unit tests for Phase 6B Multi-Agent Engineering Runtime."""

import json
import uuid

import pytest

from app.agent.exceptions import AgentExecutionException
from app.agent.models import MockChatModelProvider
from app.agent.multi_agent.coder import CoderAgent
from app.agent.multi_agent.orchestrator import EngineeringOrchestrator
from app.agent.multi_agent.planner import PlannerAgent
from app.agent.multi_agent.reviewer import ReviewerAgent
from app.agent.multi_agent.state import create_initial_multi_agent_state
from app.agent.multi_agent.tester import TesterAgent
from app.agent.multi_agent.types import (
    AgentRoleEnum,
    ReviewFindingSeverity,
    TaskLifecycleState,
)


@pytest.mark.asyncio
async def test_multi_agent_state_initialization():
    """Verifies that create_initial_multi_agent_state properly formats defaults and bounds."""
    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Add rate limiting to API",
    )

    assert state["lifecycle_state"] == TaskLifecycleState.TASK_CREATED.value
    assert state["active_agent"] == AgentRoleEnum.SUPERVISOR.value
    assert state["iteration_count"] == 0
    assert state["approval_status"]["PLAN"] == "PENDING"
    assert state["approval_status"]["DIFF"] == "PENDING"
    assert state["approval_status"]["COMMIT"] == "PENDING"
    assert state["approval_status"]["PUSH"] == "PENDING"
    assert state["approval_status"]["PR_CREATE"] == "PENDING"


@pytest.mark.asyncio
async def test_planner_agent_execution_and_tool_guard():
    """Verifies PlannerAgent synthesizes structured plan and rejects mutating tool calls."""
    mock_provider = MockChatModelProvider(
        default_response='{"summary": "Rate Limiter Plan", "problem_statement": "Add rate limiter", "approach": "Add dependency", "affected_files": [{"file_path": "app/api/v1/agent.py", "change_type": "MODIFY", "reason": "Add guard", "symbols": []}], "new_files": [], "deleted_files": [], "test_strategy": "pytest -v", "risks": [], "sources": []}'
    )
    planner = PlannerAgent(model_provider=mock_provider)

    # 1. Verify tool validation rejects unauthorized tools
    with pytest.raises(AgentExecutionException) as exc_info:
        planner.validate_tool_access("apply_patch")
    assert "strictly forbidden" in str(exc_info.value)

    with pytest.raises(AgentExecutionException):
        planner.validate_tool_access("git_commit")

    planner.validate_tool_access("search_repository")
    planner.validate_tool_access("get_file")

    # 2. Execute planner step
    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Add rate limiting to API",
    )

    delta = await planner.execute(state)
    assert delta["lifecycle_state"] == TaskLifecycleState.PLAN_READY.value
    assert delta["active_agent"] == AgentRoleEnum.PLANNER.value
    assert delta["implementation_plan"]["summary"] == "Rate Limiter Plan"
    assert "app/api/v1/agent.py" in delta["affected_files"]


@pytest.mark.asyncio
async def test_coder_agent_execution_and_mutation_boundaries():
    """Verifies CoderAgent generates patch proposals but is forbidden from direct persistence tools."""
    mock_provider = MockChatModelProvider()
    coder = CoderAgent(model_provider=mock_provider)

    # 1. Verify mutation tools are forbidden
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("apply_patch")
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("git_commit")
    with pytest.raises(AgentExecutionException):
        coder.validate_tool_access("create_pull_request")

    coder.validate_tool_access("propose_patch")

    # 2. Execute coder step
    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Add rate limiting to API",
    )
    state["implementation_plan"] = {
        "summary": "Rate Limiter Plan",
        "affected_files": [{"file_path": "app/api/v1/agent.py", "reason": "Add guard"}],
    }

    delta = await coder.execute(state)
    assert delta["lifecycle_state"] == TaskLifecycleState.PATCH_READY.value
    assert delta["active_agent"] == AgentRoleEnum.CODER.value
    assert delta["active_patch"] is not None
    assert delta["active_patch"]["status"] == "PROPOSED"


@pytest.mark.asyncio
async def test_tester_agent_sandboxed_execution():
    """Verifies TesterAgent executes allowlisted test commands and handles results."""
    mock_provider = MockChatModelProvider()
    tester = TesterAgent(model_provider=mock_provider)

    # 1. Verify tool validation
    tester.validate_tool_access("run_tests")
    with pytest.raises(AgentExecutionException):
        tester.validate_tool_access("propose_patch")

    # 2. Execute test step
    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Test feature",
    )
    delta = await tester.execute(state)
    assert delta["lifecycle_state"] == TaskLifecycleState.TEST_PASSED.value
    assert delta["last_test_passed"] is True
    assert len(delta["test_results"]) == 1


@pytest.mark.asyncio
async def test_reviewer_agent_adversarial_security_auditing():
    """Verifies ReviewerAgent detects security findings and assigns appropriate approval state."""
    vulnerable_review = {
        "status": "CHANGES_REQUESTED",
        "summary": "Detected potential SQL injection vulnerability in raw query parameter.",
        "findings": [
            {
                "severity": "CRITICAL",
                "category": "SECURITY",
                "file_path": "app/api/v1/agent.py",
                "start_line": 45,
                "end_line": 48,
                "description": "Unescaped string formatting in SQL query.",
                "recommendation": "Use parameterized SQLAlchemy select statement.",
            }
        ],
    }

    mock_provider = MockChatModelProvider(default_response=json.dumps(vulnerable_review))
    reviewer = ReviewerAgent(model_provider=mock_provider)

    # Verify Reviewer has zero mutation tools
    with pytest.raises(AgentExecutionException):
        reviewer.validate_tool_access("apply_patch")
    with pytest.raises(AgentExecutionException):
        reviewer.validate_tool_access("propose_patch")

    state = create_initial_multi_agent_state(
        task_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt="Review patch",
    )
    state["active_patch"] = {"diff_content": "+ query = f'SELECT * FROM users WHERE name={name}'"}

    delta = await reviewer.execute(state)
    assert delta["lifecycle_state"] == TaskLifecycleState.REVIEW_FAILED.value
    assert delta["review_status"] == "CHANGES_REQUESTED"
    assert len(delta["review_findings"]) == 1
    assert delta["review_findings"][0]["severity"] == ReviewFindingSeverity.CRITICAL.value
    assert delta["review_iteration_count"] == 1


@pytest.mark.asyncio
async def test_orchestrator_deterministic_routing():
    """Verifies EngineeringOrchestrator routes through Planner, pauses at Gate 1, and routes to Coder."""
    mock_provider = MockChatModelProvider(
        default_response='{"summary": "Plan A", "problem_statement": "Problem A", "approach": "Approach A", "affected_files": [], "new_files": [], "deleted_files": [], "test_strategy": "pytest -v", "risks": [], "sources": []}'
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
        prompt="Build rate limiting feature",
    )

    # 1. First invocation -> executes Planner -> pauses at Gate 1 (PLAN_READY)
    result_1 = await orchestrator.ainvoke(state)
    assert result_1["lifecycle_state"] == TaskLifecycleState.PLAN_READY.value
    assert result_1["implementation_plan"] is not None

    # 2. Grant Gate 1 Approval -> executes Coder -> pauses at Gate 2 (PATCH_READY)
    result_1["approval_status"]["PLAN"] = "APPROVED"
    result_2 = await orchestrator.ainvoke(result_1)
    assert result_2["lifecycle_state"] == TaskLifecycleState.PATCH_READY.value
    assert result_2["active_patch"] is not None
