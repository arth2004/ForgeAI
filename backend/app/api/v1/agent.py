from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
)
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["Agent Chat"])


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
