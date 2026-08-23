"""MultiAgentState definition and factory utilities for Phase 6."""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage

from app.agent.multi_agent.types import AgentRoleEnum, TaskLifecycleState


class MultiAgentState(TypedDict):
    """Shared state container passed between Orchestrator and specialized subagents."""

    task_id: str
    session_id: str
    user_id: str
    organization_id: str
    project_id: str
    repository_id: str
    branch_id: str | None
    workspace_id: str | None
    title: str
    prompt: str

    active_agent: str
    lifecycle_state: str

    # Message sequence across agent interactions
    messages: Annotated[list[BaseMessage], operator.add]

    # Planning Phase outputs
    implementation_plan: dict[str, Any] | None
    investigation_summary: str | None
    affected_files: list[str]

    # Patching Phase outputs
    proposed_patches: list[dict[str, Any]]
    active_patch_id: str | None
    active_patch: dict[str, Any] | None

    # Testing Phase outputs
    test_results: list[dict[str, Any]]
    last_test_passed: bool | None
    test_repair_count: int

    # Reviewing Phase outputs
    review_findings: list[dict[str, Any]]
    review_status: str | None
    review_iteration_count: int

    # Guard counters and lifecycle
    iteration_count: int
    tool_call_count: int
    total_tokens_used: int
    failure_reason: str | None
    approval_status: dict[str, str]

    final_summary: str | None
    metadata: dict[str, Any]


def create_initial_multi_agent_state(
    task_id: str,
    session_id: str,
    user_id: str,
    organization_id: str,
    project_id: str,
    repository_id: str,
    prompt: str,
    branch_id: str | None = None,
    workspace_id: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MultiAgentState:
    """Factory function to build a pristine, validated MultiAgentState."""
    clean_title = title or (prompt[:60] + "..." if len(prompt) > 60 else prompt)

    return MultiAgentState(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        organization_id=organization_id,
        project_id=project_id,
        repository_id=repository_id,
        branch_id=branch_id,
        workspace_id=workspace_id,
        title=clean_title,
        prompt=prompt,
        active_agent=AgentRoleEnum.SUPERVISOR.value,
        lifecycle_state=TaskLifecycleState.TASK_CREATED.value,
        messages=[HumanMessage(content=prompt)],
        implementation_plan=None,
        investigation_summary=None,
        affected_files=[],
        proposed_patches=[],
        active_patch_id=None,
        active_patch=None,
        test_results=[],
        last_test_passed=None,
        test_repair_count=0,
        review_findings=[],
        review_status=None,
        review_iteration_count=0,
        iteration_count=0,
        tool_call_count=0,
        total_tokens_used=0,
        failure_reason=None,
        approval_status={
            "PLAN": "PENDING",
            "DIFF": "PENDING",
            "COMMIT": "PENDING",
            "PUSH": "PENDING",
            "PR_CREATE": "PENDING",
        },
        final_summary=None,
        metadata=metadata or {},
    )
