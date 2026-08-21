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
    AgentPlanRequest,
    AgentPlanResponse,
    AgentWorkspaceCreateRequest,
    AgentWorkspaceResponse,
)
from app.services.agent_service import AgentService
from app.services.planning_service import PlanningService
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

