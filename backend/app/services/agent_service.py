import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import AgentExecutionException
from app.agent.graph import build_agent_graph
from app.agent.models import BaseChatModelProvider, sanitize_secret_text
from app.agent.state import create_initial_state
from app.core.config import settings
from app.core.exceptions import (
    AgentTimeoutException,
    ConflictException,
    ForbiddenException,
    ForgeAIException,
    NotFoundException,
)
from app.models.agent import AgentSession
from app.models.auth import Membership, User
from app.models.project import Project, Repository, RepositoryBranch
from app.schemas.agent import (
    AgentChatMetadata,
    AgentChatRequest,
    AgentChatResponse,
    AgentSourceReference,
)

logger = logging.getLogger(__name__)


class AgentService:
    """Service layer orchestrating authorization, session context, and agent execution."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve_and_authorize_context(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        repository_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> AgentSession:
        """Validates organizational membership, repository/branch hierarchy, and session binding."""
        # 1. Authorize project access
        project = await self.db.get(Project, project_id)
        if not project:
            raise NotFoundException("Project", project_id)

        membership_q = select(Membership).where(
            Membership.organization_id == project.organization_id,
            Membership.user_id == user_id,
        )
        membership_res = await self.db.execute(membership_q)
        if not membership_res.scalars().first():
            raise ForbiddenException("You do not have access to this project.")

        # 2. Session validation & reuse
        if session_id is not None:
            session = await self.db.get(AgentSession, session_id)
            if not session:
                raise NotFoundException("AgentSession", session_id)

            if session.user_id != user_id:
                raise ForbiddenException("You do not have access to this agent session.")

            if session.project_id != project_id:
                raise ConflictException(
                    f"Session {session_id} belongs to project {session.project_id}, not {project_id}."
                )

            if repository_id is not None and session.repository_id != repository_id:
                raise ConflictException(
                    f"Session {session_id} is bound to repository {session.repository_id}, not {repository_id}."
                )

            if (
                branch_id is not None
                and session.branch_id is not None
                and session.branch_id != branch_id
            ):
                raise ConflictException(
                    f"Session {session_id} is bound to branch {session.branch_id}, not {branch_id}."
                )

            return session

        # 3. Resolve Target Repository
        target_repo: Repository
        if repository_id is not None:
            repo_q = select(Repository).where(Repository.id == repository_id)
            repo_res = await self.db.execute(repo_q)
            found_repo = repo_res.scalars().first()
            if not found_repo:
                raise NotFoundException("Repository", repository_id)
            if found_repo.project_id != project_id:
                raise ConflictException(f"Repository {repository_id} belongs to another project.")
            target_repo = found_repo
        else:
            primary_repo_q = (
                select(Repository)
                .where(Repository.project_id == project_id)
                .order_by(Repository.created_at.asc())
            )
            primary_res = await self.db.execute(primary_repo_q)
            first_repo = primary_res.scalars().first()
            if not first_repo:
                raise NotFoundException("Repository for project", project_id)
            target_repo = first_repo

        # 4. Resolve Target Branch
        target_branch_id: uuid.UUID | None = None
        if branch_id is not None:
            branch_q = select(RepositoryBranch).where(
                RepositoryBranch.id == branch_id,
                RepositoryBranch.repository_id == target_repo.id,
            )
            branch_res = await self.db.execute(branch_q)
            found_branch = branch_res.scalars().first()
            if not found_branch:
                raise NotFoundException("RepositoryBranch", branch_id)
            target_branch_id = found_branch.id
        else:
            default_branch_name = target_repo.default_branch or "main"
            default_branch_q = select(RepositoryBranch).where(
                RepositoryBranch.repository_id == target_repo.id,
                RepositoryBranch.name == default_branch_name,
            )
            default_branch_res = await self.db.execute(default_branch_q)
            default_branch = default_branch_res.scalars().first()
            if default_branch:
                target_branch_id = default_branch.id
            else:
                first_branch_q = (
                    select(RepositoryBranch)
                    .where(RepositoryBranch.repository_id == target_repo.id)
                    .order_by(RepositoryBranch.created_at.asc())
                )
                first_branch_res = await self.db.execute(first_branch_q)
                first_branch = first_branch_res.scalars().first()
                if first_branch:
                    target_branch_id = first_branch.id

        # 5. Create and persist new AgentSession
        new_session = AgentSession(
            user_id=user_id,
            project_id=project_id,
            repository_id=target_repo.id,
            branch_id=target_branch_id,
        )
        self.db.add(new_session)
        await self.db.commit()
        await self.db.refresh(new_session)

        return new_session

    @staticmethod
    def _extract_deduplicated_sources(
        retrieved_context: list[dict[str, Any]],
    ) -> list[AgentSourceReference]:
        """Extracts and deduplicates citations from accumulated agent context chunks."""
        seen: set[tuple[str, int | None, int | None, str | None]] = set()
        sources: list[AgentSourceReference] = []

        for item in retrieved_context:
            if not isinstance(item, dict):
                continue
            file_path = item.get("file_path")
            if not file_path:
                continue

            symbol_name = item.get("symbol_name")
            start_line = item.get("start_line")
            end_line = item.get("end_line")
            commit_sha = item.get("commit_sha")

            # Support line_range dict from get_file tool
            if start_line is None and "line_range" in item and isinstance(item["line_range"], dict):
                start_line = item["line_range"].get("start")
                end_line = item["line_range"].get("end")

            key = (file_path, start_line, end_line, symbol_name)
            if key not in seen:
                seen.add(key)
                sources.append(
                    AgentSourceReference(
                        file_path=file_path,
                        symbol_name=symbol_name,
                        start_line=start_line,
                        end_line=end_line,
                        commit_sha=commit_sha,
                    )
                )

        return sources

    async def execute_chat(
        self,
        user: User,
        request: AgentChatRequest,
        model_provider_override: BaseChatModelProvider | None = None,
    ) -> AgentChatResponse:
        """Executes a non-streaming agent chat turn under authorization and timeout constraints."""
        session = await self.resolve_and_authorize_context(
            user_id=user.id,
            project_id=request.project_id,
            repository_id=request.repository_id,
            branch_id=request.branch_id,
            session_id=request.session_id,
        )

        initial_state = create_initial_state(
            user_query=request.message,
            repository_id=str(session.repository_id),
            branch_id=str(session.branch_id) if session.branch_id else None,
            project_id=str(session.project_id),
            user_id=str(user.id),
            metadata={"session_id": str(session.id)},
        )

        graph = build_agent_graph(
            model_provider=model_provider_override,
            db_session=self.db,
            user_id=user.id,
        )

        start_time = time.perf_counter()
        timeout_seconds = getattr(settings, "AGENT_TIMEOUT_SECONDS", 60.0)

        try:
            result_state = await asyncio.wait_for(
                graph.ainvoke(initial_state),
                timeout=timeout_seconds,
            )
        except TimeoutError as te:
            logger.error(
                f"[AgentService] Execution timed out after {timeout_seconds}s for session {session.id}"
            )
            raise AgentTimeoutException(
                f"Agent reasoning exceeded maximum timeout limit of {timeout_seconds} seconds."
            ) from te
        except AgentExecutionException:
            raise
        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            logger.error(f"[AgentService] Execution failure: {sanitized}")
            raise AgentExecutionException(
                message=f"Agent execution encountered an error: {sanitized}",
                node_name="agent_service",
            ) from exc

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        retrieved_context = result_state.get("retrieved_context", [])
        tool_results = result_state.get("tool_results", [])
        sources = self._extract_deduplicated_sources(retrieved_context)

        final_answer = result_state.get("final_answer") or (
            str(result_state.get("messages", [])[-1].content)
            if result_state.get("messages")
            else "No answer generated."
        )

        metadata = AgentChatMetadata(
            iterations=result_state.get("iteration_count", 1),
            tool_calls=len(tool_results),
            duration_ms=duration_ms,
            retrieved_sources_count=len(retrieved_context),
        )

        return AgentChatResponse(
            session_id=session.id,
            project_id=session.project_id,
            repository_id=session.repository_id,
            branch_id=session.branch_id,
            answer=final_answer,
            sources=sources,
            metadata=metadata,
        )

    async def stream_chat(
        self,
        user: User,
        request: AgentChatRequest,
        model_provider_override: BaseChatModelProvider | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streams agent reasoning events and completion payload via Server-Sent Events (SSE)."""

        def _format_sse(event_type: str, payload: dict[str, Any]) -> str:
            return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        session: AgentSession
        try:
            session = await self.resolve_and_authorize_context(
                user_id=user.id,
                project_id=request.project_id,
                repository_id=request.repository_id,
                branch_id=request.branch_id,
                session_id=request.session_id,
            )
        except ForgeAIException as fe:
            yield _format_sse("agent.error", {"error": fe.message, "status_code": fe.status_code})
            return
        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            yield _format_sse("agent.error", {"error": sanitized, "status_code": 500})
            return

        yield _format_sse(
            "session.created",
            {
                "session_id": str(session.id),
                "project_id": str(session.project_id),
                "repository_id": str(session.repository_id),
                "branch_id": str(session.branch_id) if session.branch_id else None,
            },
        )

        yield _format_sse(
            "agent.started",
            {
                "session_id": str(session.id),
                "iteration": 1,
            },
        )

        initial_state = create_initial_state(
            user_query=request.message,
            repository_id=str(session.repository_id),
            branch_id=str(session.branch_id) if session.branch_id else None,
            project_id=str(session.project_id),
            user_id=str(user.id),
            metadata={"session_id": str(session.id)},
        )

        graph = build_agent_graph(
            model_provider=model_provider_override,
            db_session=self.db,
            user_id=user.id,
        )

        start_time = time.perf_counter()
        timeout_seconds = getattr(settings, "AGENT_TIMEOUT_SECONDS", 60.0)

        accumulated_retrieved_context: list[dict[str, Any]] = []
        accumulated_tool_results: list[dict[str, Any]] = []
        final_answer: str = ""
        iteration_count: int = 1

        try:
            stream_gen = graph.astream(initial_state, stream_mode="updates")

            async def _consume_stream():
                nonlocal final_answer, iteration_count
                async for update in stream_gen:
                    if not isinstance(update, dict):
                        continue

                    # Agent node turn update
                    if "agent" in update:
                        agent_update = update["agent"]
                        iteration_count = agent_update.get("iteration_count", iteration_count)
                        msgs = agent_update.get("messages", [])
                        if msgs:
                            last_m = msgs[-1]
                            tool_calls = getattr(last_m, "tool_calls", None) or []
                            if tool_calls:
                                for tc in tool_calls:
                                    yield _format_sse(
                                        "agent.tool_call",
                                        {
                                            "tool": tc.get("name"),
                                            "call_id": tc.get("id"),
                                            "iteration": iteration_count,
                                            "args": tc.get("args", {}),
                                        },
                                    )
                            else:
                                final_answer = str(last_m.content)

                    # Tools node turn update
                    if "tools" in update:
                        tools_update = update["tools"]
                        new_tools = tools_update.get("tool_results", [])
                        # Check newly executed tool items
                        for res in new_tools[len(accumulated_tool_results) :]:
                            accumulated_tool_results.append(res)
                            yield _format_sse(
                                "agent.tool_result",
                                {
                                    "tool": res.get("tool"),
                                    "status": "success" if res.get("success") else "failed",
                                    "duration_ms": res.get("duration_ms", 0.0),
                                    "error": res.get("error"),
                                },
                            )
                        new_context = tools_update.get("retrieved_context", [])
                        accumulated_retrieved_context.clear()
                        accumulated_retrieved_context.extend(new_context)

            # Consume async generator with timeout
            async for sse_event in _consume_stream():
                yield sse_event

        except TimeoutError:
            yield _format_sse(
                "agent.error",
                {
                    "error": f"Agent reasoning exceeded timeout limit of {timeout_seconds}s.",
                    "status_code": 504,
                },
            )
            return
        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            logger.error(f"[AgentService:stream_chat] Stream error: {sanitized}")
            yield _format_sse("agent.error", {"error": sanitized, "status_code": 500})
            return

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        sources = self._extract_deduplicated_sources(accumulated_retrieved_context)

        metadata = AgentChatMetadata(
            iterations=iteration_count,
            tool_calls=len(accumulated_tool_results),
            duration_ms=duration_ms,
            retrieved_sources_count=len(accumulated_retrieved_context),
        )

        completed_payload = {
            "session_id": str(session.id),
            "project_id": str(session.project_id),
            "repository_id": str(session.repository_id),
            "branch_id": str(session.branch_id) if session.branch_id else None,
            "answer": final_answer,
            "sources": [s.model_dump() for s in sources],
            "metadata": metadata.model_dump(),
        }

        yield _format_sse("agent.completed", completed_payload)
