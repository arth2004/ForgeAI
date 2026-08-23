import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.multi_agent.types import AgentTaskCreateRequest, AgentTaskResponse
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.schemas.agent import (
    AgentApprovalActionRequest,
    AgentApprovalResponse,
    AgentBranchCreateRequest,
    AgentBranchResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentCommitRequest,
    AgentCommitResponse,
    AgentGitStatusResponse,
    AgentPatchApplyResponse,
    AgentPatchProposalRequest,
    AgentPatchResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentPullRequestCreateRequest,
    AgentPullRequestResponse,
    AgentPushRequest,
    AgentPushResponse,
    AgentTestExecutionRequest,
    AgentTestExecutionResponse,
    AgentWorkspaceCreateRequest,
    AgentWorkspaceResponse,
    PatchDiffResponse,
)
from app.services.agent_service import AgentService
from app.services.git_service import GitService
from app.services.github_pr_service import GitHubPRService
from app.services.patch_service import PatchService
from app.services.planning_service import PlanningService
from app.services.test_execution_service import TestExecutionService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/agent", tags=["Agent Operations"])


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Agent Chat Turn",
    description="Invokes the Forge AI repository intelligence agent for an authenticated user. Supports JSON and SSE streaming.",
)
async def chat_with_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse | StreamingResponse:
    """Invokes the repository reasoning agent synchronously or as an SSE stream."""
    agent_service = AgentService(db=db)

    if request.stream:
        return StreamingResponse(
            agent_service.stream_chat(user=current_user, request=request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return await agent_service.execute_chat(user=current_user, request=request)


@router.post(
    "/chat/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream Agent Chat Turn (SSE)",
    description="Direct endpoint returning a Server-Sent Events (SSE) stream of reasoning and tool lifecycle events.",
)
async def stream_chat_with_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streams the agent reasoning loop and tool executions as Server-Sent Events."""
    agent_service = AgentService(db=db)
    return StreamingResponse(
        agent_service.stream_chat(user=current_user, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# Phase 5B: Planning Endpoints
# ============================================================================


@router.post(
    "/plan",
    response_model=AgentPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Implementation Plan",
    description="Invokes the Planning Agent to investigate the codebase and synthesize a grounded ImplementationPlan with Gate 1 approval.",
)
async def generate_plan(
    request: AgentPlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPlanResponse:
    """Investigates repository and generates a structured ImplementationPlan."""
    planning_service = PlanningService(db=db)
    return await planning_service.generate_plan(user=current_user, request=request)


@router.post(
    "/plan/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream Plan Generation (SSE)",
    description="Streams planning investigation events and yields the synthesized plan with pending Gate 1 approval.",
)
async def stream_plan_generation(
    request: AgentPlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streams the planning reasoning loop and plan creation as Server-Sent Events."""
    planning_service = PlanningService(db=db)
    return StreamingResponse(
        planning_service.stream_plan(user=current_user, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



# ============================================================================
# Phase 5B: Human Approval Gate 1 Endpoints
# ============================================================================


@router.get(
    "/approvals/{approval_id}",
    response_model=AgentApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Approval Details",
    description="Fetches details and status of an AgentApproval gate.",
)
async def get_approval(
    approval_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentApprovalResponse:
    """Retrieves approval gate details."""
    planning_service = PlanningService(db=db)
    return await planning_service.get_approval(user_id=current_user.id, approval_id=approval_id)


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=AgentApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve Plan Gate",
    description="Approves a pending ImplementationPlan gate, enabling subsequent workspace creation.",
)
async def approve_plan(
    approval_id: uuid.UUID,
    payload: AgentApprovalActionRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentApprovalResponse:
    """Explicitly approves the implementation plan."""
    planning_service = PlanningService(db=db)
    reason = payload.reason if payload else None
    return await planning_service.approve_plan(
        user_id=current_user.id, approval_id=approval_id, reason=reason
    )


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=AgentApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject Plan Gate",
    description="Rejects a pending ImplementationPlan gate, preventing workspace creation.",
)
async def reject_plan(
    approval_id: uuid.UUID,
    payload: AgentApprovalActionRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentApprovalResponse:
    """Explicitly rejects the implementation plan."""
    planning_service = PlanningService(db=db)
    reason = payload.reason if payload else None
    return await planning_service.reject_plan(
        user_id=current_user.id, approval_id=approval_id, reason=reason
    )


# ============================================================================
# Phase 5B: Ephemeral Workspace Endpoints
# ============================================================================


@router.post(
    "/workspaces",
    response_model=AgentWorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Isolated Ephemeral Workspace",
    description="Provisions an isolated ephemeral workspace after verified Gate 1 plan approval.",
)
async def create_workspace(
    request: AgentWorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceResponse:
    """Creates an isolated workspace."""
    workspace_service = WorkspaceService(db=db)
    return await workspace_service.create_workspace(
        user_id=current_user.id,
        session_id=request.session_id,
        approval_id=request.approval_id,
    )


@router.get(
    "/workspaces/{workspace_id}",
    response_model=AgentWorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workspace Details",
    description="Retrieves status and metadata of an isolated ephemeral workspace.",
)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceResponse:
    """Retrieves workspace metadata."""
    workspace_service = WorkspaceService(db=db)
    return await workspace_service.get_workspace(
        user_id=current_user.id, workspace_id=workspace_id
    )


@router.delete(
    "/workspaces/{workspace_id}",
    response_model=AgentWorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Destroy Ephemeral Workspace",
    description="Idempotently destroys the workspace directory and marks the database record as DESTROYED.",
)
async def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceResponse:
    """Destroys and cleans up an isolated workspace."""
    workspace_service = WorkspaceService(db=db)
    return await workspace_service.delete_workspace(
        user_id=current_user.id, workspace_id=workspace_id
    )


# --- Phase 5C Endpoints: Safe Patch Synthesis & Sandboxed Test Execution ---


@router.post(
    "/patches/propose",
    response_model=AgentPatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose Structured Patch",
    description="Validates a structured patch proposal, verifies drift hashes, generates a unified diff, and creates a pending DIFF approval gate.",
)
async def propose_patch(
    request: AgentPatchProposalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPatchResponse:
    """Proposes a structured patch for validation and review."""
    patch_service = PatchService(db=db)
    return await patch_service.propose_patch(
        user_id=current_user.id,
        request=request,
    )


@router.get(
    "/patches/{patch_id}",
    response_model=AgentPatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Patch Proposal Details",
    description="Retrieves status and metadata of a proposed AgentPatch.",
)
async def get_patch(
    patch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPatchResponse:
    """Retrieves an AgentPatch proposal."""
    patch_service = PatchService(db=db)
    return await patch_service.get_patch(
        user_id=current_user.id,
        patch_id=patch_id,
    )


@router.get(
    "/patches/{patch_id}/diff",
    response_model=PatchDiffResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Server-Generated Patch Diff",
    description="Retrieves the authoritative server-generated unified diff preview.",
)
async def get_patch_diff(
    patch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatchDiffResponse:
    """Retrieves the unified diff representation of a patch."""
    patch_service = PatchService(db=db)
    return await patch_service.get_patch_diff(
        user_id=current_user.id,
        patch_id=patch_id,
    )


@router.post(
    "/patches/{patch_id}/approve",
    response_model=AgentPatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve Patch Diff Gate",
    description="Explicit human approval for a proposed patch diff, enabling atomic application.",
)
async def approve_patch(
    patch_id: uuid.UUID,
    request: AgentApprovalActionRequest = AgentApprovalActionRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPatchResponse:
    """Explicitly approves a proposed patch."""
    patch_service = PatchService(db=db)
    return await patch_service.approve_patch(
        user_id=current_user.id,
        patch_id=patch_id,
        reason=request.reason,
    )


@router.post(
    "/patches/{patch_id}/reject",
    response_model=AgentPatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject Patch Diff Gate",
    description="Explicit human rejection of a proposed patch.",
)
async def reject_patch(
    patch_id: uuid.UUID,
    request: AgentApprovalActionRequest = AgentApprovalActionRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPatchResponse:
    """Explicitly rejects a proposed patch."""
    patch_service = PatchService(db=db)
    return await patch_service.reject_patch(
        user_id=current_user.id,
        patch_id=patch_id,
        reason=request.reason,
    )


@router.post(
    "/patches/{patch_id}/apply",
    response_model=AgentPatchApplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply Approved Patch Atomically",
    description="Authoritative gate: applies an APPROVED patch atomically to the workspace filesystem with automatic rollback on error.",
)
async def apply_patch(
    patch_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPatchApplyResponse:
    """Applies an approved patch atomically to the workspace."""
    patch_service = PatchService(db=db)
    return await patch_service.apply_patch(
        user_id=current_user.id,
        patch_id=patch_id,
    )


@router.post(
    "/workspaces/{workspace_id}/tests",
    response_model=AgentTestExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute Sandboxed Test Runner",
    description="Runs an allowlisted declarative test command (pytest, ruff, npm_test, cargo_test) inside the isolated container sandbox.",
)
async def execute_test(
    workspace_id: uuid.UUID,
    request: AgentTestExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentTestExecutionResponse:
    """Executes a test runner inside the workspace sandbox."""
    test_service = TestExecutionService(db=db)
    return await test_service.execute_test(
        user_id=current_user.id,
        workspace_id=workspace_id,
        request=request,
    )


@router.get(
    "/tests/{test_id}",
    response_model=AgentTestExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Test Execution Report",
    description="Retrieves the report, status, and output logs of a sandboxed test execution.",
)
async def get_test_execution(
    test_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentTestExecutionResponse:
    """Retrieves a test execution report."""
    test_service = TestExecutionService(db=db)
    return await test_service.get_test_execution(
        user_id=current_user.id,
        test_id=test_id,
    )


# --- Phase 5D Endpoints: Git Branch, Commit & Pull Request Integration ---


@router.post(
    "/workspaces/{workspace_id}/branch",
    response_model=AgentBranchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Workspace Git Branch",
    description="Creates an isolated Git branch within the active ephemeral workspace.",
)
async def create_branch(
    workspace_id: uuid.UUID,
    request: AgentBranchCreateRequest = AgentBranchCreateRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentBranchResponse:
    """Creates a local Git branch in the workspace."""
    git_service = GitService(db=db)
    return await git_service.create_branch(
        user_id=current_user.id,
        workspace_id=workspace_id,
        branch_name=request.branch_name,
    )


@router.get(
    "/workspaces/{workspace_id}/git-status",
    response_model=AgentGitStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workspace Git Status",
    description="Returns structured server-side Git working tree status for the workspace.",
)
async def get_git_status(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentGitStatusResponse:
    """Inspects Git status of the workspace."""
    git_service = GitService(db=db)
    return await git_service.get_git_status(
        user_id=current_user.id,
        workspace_id=workspace_id,
    )


@router.post(
    "/workspaces/{workspace_id}/commit",
    response_model=AgentCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Commit Approved Changes",
    description="Authoritative gate: commits approved workspace modifications after verifying explicit COMMIT approval.",
)
async def commit_changes(
    workspace_id: uuid.UUID,
    request: AgentCommitRequest = AgentCommitRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentCommitResponse:
    """Commits approved changes in the workspace."""
    git_service = GitService(db=db)
    return await git_service.commit_changes(
        user_id=current_user.id,
        workspace_id=workspace_id,
        message=request.message,
        patch_id=request.patch_id,
    )


@router.post(
    "/workspaces/{workspace_id}/push",
    response_model=AgentPushResponse,
    status_code=status.HTTP_200_OK,
    summary="Push Branch to Remote",
    description="Authoritative gate: pushes committed branch to remote repository after verifying explicit PUSH approval.",
)
async def push_branch(
    workspace_id: uuid.UUID,
    request: AgentPushRequest = AgentPushRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPushResponse:
    """Pushes workspace branch to remote repository."""
    git_service = GitService(db=db)
    return await git_service.push_branch(
        user_id=current_user.id,
        workspace_id=workspace_id,
        remote=request.remote,
    )


@router.post(
    "/pulls/{workspace_id}/create",
    response_model=AgentPullRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create GitHub Pull Request",
    description="Authoritative gate: creates a GitHub Pull Request from the pushed branch after verifying explicit PR_CREATE approval.",
)
async def create_pull_request(
    workspace_id: uuid.UUID,
    request: AgentPullRequestCreateRequest = AgentPullRequestCreateRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPullRequestResponse:
    """Creates a GitHub Pull Request."""
    pr_service = GitHubPRService(db=db)
    return await pr_service.create_pull_request(
        user_id=current_user.id,
        workspace_id=workspace_id,
        request=request,
    )


@router.get(
    "/pulls/{pull_id}",
    response_model=AgentPullRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Pull Request Details",
    description="Retrieves status and metadata of a created AgentPullRequest.",
)
async def get_pull_request(
    pull_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentPullRequestResponse:
    """Retrieves an AgentPullRequest record."""
    pr_service = GitHubPRService(db=db)
    return await pr_service.get_pull_request(
        user_id=current_user.id,
        pr_id=pull_id,
    )


# --- Phase 6B Multi-Agent Task Endpoints ---


@router.post(
    "/tasks",
    response_model=AgentTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Multi-Agent Engineering Task",
    description="Initializes a multi-agent engineering task managed by the EngineeringOrchestrator.",
)
async def create_agent_task(
    request: AgentTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentTaskResponse:
    """Initializes an AgentTask for multi-agent execution."""
    from sqlalchemy import select

    from app.core.exceptions import ForbiddenException, NotFoundException
    from app.models.agent import AgentSession, AgentTask, TaskLifecycleState
    from app.services.project_service import ProjectService

    # Verify project and tenant isolation
    project_service = ProjectService(db)
    project = await project_service.get_by_id(current_user.id, request.project_id)
    if not project:
        raise NotFoundException("Project", request.project_id)

    # Resolve or create session
    session_id = request.session_id
    if session_id is None:
        session = AgentSession(
            user_id=current_user.id,
            project_id=request.project_id,
            repository_id=request.repository_id,
            branch_id=request.branch_id,
        )
        db.add(session)
        await db.flush()
        session_id = session.id
    else:
        session_stmt = select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == current_user.id,
        )
        session_res = await db.execute(session_stmt)
        if not session_res.scalar_one_or_none():
            raise ForbiddenException("Access to specified agent session forbidden.")

    task = AgentTask(
        session_id=session_id,
        user_id=current_user.id,
        organization_id=project.organization_id,
        project_id=request.project_id,
        repository_id=request.repository_id,
        branch_id=request.branch_id,
        title=request.title or (request.prompt[:60] + "..." if len(request.prompt) > 60 else request.prompt),
        prompt=request.prompt,
        lifecycle_state=TaskLifecycleState.TASK_CREATED.value,
        active_agent="SUPERVISOR",
        iteration_count=0,
        tool_call_count=0,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return AgentTaskResponse.model_validate(task)


@router.get(
    "/tasks/{task_id}",
    response_model=AgentTaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Agent Task Details",
    description="Retrieves status and lifecycle metrics for an AgentTask.",
)
async def get_agent_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentTaskResponse:
    """Retrieves an AgentTask record with tenant authorization checks."""
    from sqlalchemy import select

    from app.core.exceptions import ForbiddenException, NotFoundException
    from app.models.agent import AgentTask
    from app.services.organization_service import OrganizationService

    stmt = select(AgentTask).where(AgentTask.id == task_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise NotFoundException(f"AgentTask {task_id} not found.")

    org_service = OrganizationService(db)
    user_orgs = await org_service.list_for_user(current_user.id)
    user_org_ids = [o.id for o in user_orgs]

    if task.organization_id not in user_org_ids:
        raise ForbiddenException("Cross-tenant access to AgentTask forbidden.")

    if task.user_id != current_user.id:
        raise ForbiddenException("Cross-session access to AgentTask forbidden.")

    return AgentTaskResponse.model_validate(task)


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=AgentTaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Agent Task",
    description="Gracefully terminates a running AgentTask and transitions to CANCELLED state.",
)
async def cancel_agent_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentTaskResponse:
    """Cancels an AgentTask."""
    from sqlalchemy import select

    from app.core.exceptions import ForbiddenException, NotFoundException
    from app.models.agent import AgentTask, TaskLifecycleState
    from app.models.base import utc_now
    from app.services.organization_service import OrganizationService

    stmt = select(AgentTask).where(AgentTask.id == task_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise NotFoundException(f"AgentTask {task_id} not found.")

    org_service = OrganizationService(db)
    user_orgs = await org_service.list_for_user(current_user.id)
    user_org_ids = [o.id for o in user_orgs]

    if task.organization_id not in user_org_ids:
        raise ForbiddenException("Cross-tenant access to AgentTask forbidden.")

    task.lifecycle_state = TaskLifecycleState.CANCELLED.value
    task.failure_reason = "Cancelled by user request."
    task.completed_at = utc_now()

    await db.commit()
    await db.refresh(task)

    return AgentTaskResponse.model_validate(task)





