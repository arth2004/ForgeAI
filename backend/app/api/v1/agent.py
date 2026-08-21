import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.schemas.agent import (
    AgentApprovalActionRequest,
    AgentApprovalResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentPatchApplyResponse,
    AgentPatchProposalRequest,
    AgentPatchResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentTestExecutionRequest,
    AgentTestExecutionResponse,
    AgentWorkspaceCreateRequest,
    AgentWorkspaceResponse,
    PatchDiffResponse,
)
from app.services.agent_service import AgentService
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


