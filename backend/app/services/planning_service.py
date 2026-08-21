import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import AgentExecutionException
from app.agent.graph import build_agent_graph
from app.agent.models import BaseChatModelProvider, sanitize_secret_text
from app.agent.planning.validator import validate_implementation_plan
from app.agent.prompts import PLANNING_AGENT_SYSTEM_PROMPT
from app.agent.state import create_initial_state
from app.core.config import settings
from app.core.exceptions import (
    AgentTimeoutException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.agent import AgentApproval, AgentSession, ApprovalStatus, ApprovalType
from app.models.auth import User
from app.models.base import utc_now
from app.schemas.agent import (
    AffectedFile,
    AgentApprovalResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    ChangeType,
    ImplementationPlan,
)
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)


class PlanningService:
    """Service layer orchestrating the planning agent loop, plan validation, and Gate 1 approvals."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.agent_service = AgentService(db=db)

    @staticmethod
    def _parse_plan_json(raw_text: str, default_summary: str = "Implementation Plan") -> dict[str, Any]:
        """Extracts and parses JSON payload representing an ImplementationPlan."""
        cleaned = raw_text.strip()
        # Try finding markdown ```json codeblock
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except Exception:
                pass

        # Try parsing full string as JSON
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                return json.loads(cleaned)
            except Exception:
                pass

        # Fallback dictionary if model emitted pure narrative
        return {
            "summary": default_summary,
            "problem_statement": cleaned[:1000] if cleaned else "Codebase modification request.",
            "approach": cleaned if cleaned else "Implement requested modifications.",
            "affected_files": [],
            "new_files": [],
            "deleted_files": [],
            "symbols": [],
            "test_strategy": "Run unit test suite against modified components.",
            "risks": [],
        }

    async def generate_plan(
        self,
        user: User,
        request: AgentPlanRequest,
        model_provider_override: BaseChatModelProvider | None = None,
    ) -> AgentPlanResponse:
        """Executes read-only investigation and synthesizes a validated ImplementationPlan."""
        # 1. Authorize and resolve session context
        session = await self.agent_service.resolve_and_authorize_context(
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
            metadata={"session_id": str(session.id), "phase": "planning"},
        )

        # 2. Build graph with planning system prompt
        graph = build_agent_graph(
            model_provider=model_provider_override,
            db_session=self.db,
            user_id=user.id,
            system_prompt=PLANNING_AGENT_SYSTEM_PROMPT,
        )

        start_time = time.perf_counter()
        timeout_seconds = getattr(settings, "AGENT_TIMEOUT_SECONDS", 60.0)

        try:
            result_state = await asyncio.wait_for(
                graph.ainvoke(initial_state),
                timeout=timeout_seconds,
            )
        except TimeoutError as te:
            raise AgentTimeoutException(
                f"Planning agent execution timed out after {timeout_seconds}s."
            ) from te
        except AgentExecutionException:
            raise
        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            logger.error(f"[PlanningService] Execution error: {sanitized}")
            raise AgentExecutionException(
                message=f"Planning agent encountered an error: {sanitized}",
                node_name="planning_service",
            ) from exc

        # 3. Extract evidence and final plan output
        retrieved_context = result_state.get("retrieved_context", [])
        sources = self.agent_service._extract_deduplicated_sources(retrieved_context)

        final_content = result_state.get("final_answer") or (
            str(result_state.get("messages", [])[-1].content)
            if result_state.get("messages")
            else ""
        )

        plan_dict = self._parse_plan_json(final_content, default_summary=f"Plan for: {request.message[:80]}")

        # Parse affected files into AffectedFile models
        parsed_affected_files: list[AffectedFile] = []
        for af_data in plan_dict.get("affected_files", []):
            if isinstance(af_data, dict):
                ct_val = af_data.get("change_type", "MODIFY")
                try:
                    ct = ChangeType(str(ct_val).upper())
                except ValueError:
                    ct = ChangeType.MODIFY
                parsed_affected_files.append(
                    AffectedFile(
                        file_path=str(af_data.get("file_path", "")),
                        change_type=ct,
                        reason=str(af_data.get("reason", "Required modification.")),
                        symbols=[str(s) for s in af_data.get("symbols", [])],
                    )
                )

        plan = ImplementationPlan(
            summary=plan_dict.get("summary", "Implementation Plan"),
            problem_statement=plan_dict.get("problem_statement", request.message),
            approach=plan_dict.get("approach", "Follow architectural best practices."),
            affected_files=parsed_affected_files,
            new_files=[str(f) for f in plan_dict.get("new_files", [])],
            deleted_files=[str(f) for f in plan_dict.get("deleted_files", [])],
            symbols=[str(s) for s in plan_dict.get("symbols", [])],
            test_strategy=plan_dict.get("test_strategy", "Execute regression test suite."),
            risks=[str(r) for r in plan_dict.get("risks", [])],
            evidence=sources,
        )

        # 4. Server-side validation
        validated_plan = validate_implementation_plan(plan, require_evidence=False)

        # 5. Create Gate 1 AgentApproval record
        approval = AgentApproval(
            id=uuid.uuid4(),
            session_id=session.id,
            workspace_id=None,
            user_id=user.id,
            approval_type=ApprovalType.PLAN.value,
            status=ApprovalStatus.PENDING.value,
            plan_payload=validated_plan.model_dump(mode="json"),
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            f"[plan.created] approval_id={approval.id} session_id={session.id} "
            f"user_id={user.id} files_affected={len(validated_plan.affected_files)} duration_ms={duration_ms}"
        )

        return AgentPlanResponse(
            session_id=session.id,
            project_id=session.project_id,
            repository_id=session.repository_id,
            branch_id=session.branch_id,
            plan=validated_plan,
            approval_id=approval.id,
            approval_status=approval.status,
            created_at=approval.created_at,
        )

    async def approve_plan(
        self,
        user_id: uuid.UUID,
        approval_id: uuid.UUID,
        reason: str | None = None,
    ) -> AgentApprovalResponse:
        """Approves a pending Plan approval gate."""
        approval = await self.db.get(AgentApproval, approval_id)
        if not approval:
            raise NotFoundException("AgentApproval", approval_id)

        if approval.user_id != user_id:
            raise ForbiddenException("You do not have permission to approve this plan.")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ConflictException(f"Approval is in '{approval.status}' status and cannot be approved.")

        approval.status = ApprovalStatus.APPROVED.value
        approval.resolved_at = utc_now()

        await self.db.commit()
        await self.db.refresh(approval)

        logger.info(f"[approval.approved] approval_id={approval.id} user_id={user_id}")
        return self._to_approval_response(approval)

    async def reject_plan(
        self,
        user_id: uuid.UUID,
        approval_id: uuid.UUID,
        reason: str | None = None,
    ) -> AgentApprovalResponse:
        """Rejects a pending Plan approval gate."""
        approval = await self.db.get(AgentApproval, approval_id)
        if not approval:
            raise NotFoundException("AgentApproval", approval_id)

        if approval.user_id != user_id:
            raise ForbiddenException("You do not have permission to reject this plan.")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ConflictException(f"Approval is in '{approval.status}' status and cannot be rejected.")

        approval.status = ApprovalStatus.REJECTED.value
        approval.resolved_at = utc_now()

        await self.db.commit()
        await self.db.refresh(approval)

        logger.info(f"[approval.rejected] approval_id={approval.id} user_id={user_id}")
        return self._to_approval_response(approval)

    async def get_approval(
        self,
        user_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> AgentApprovalResponse:
        """Fetches approval details after ownership validation."""
        approval = await self.db.get(AgentApproval, approval_id)
        if not approval:
            raise NotFoundException("AgentApproval", approval_id)

        if approval.user_id != user_id:
            raise ForbiddenException("You do not have access to this approval record.")

        return self._to_approval_response(approval)

    async def stream_plan(
        self,
        user: User,
        request: AgentPlanRequest,
        model_provider_override: BaseChatModelProvider | None = None,
    ):
        """Streams planning investigation events and yields structured plan + approval gate."""

        def _format_sse(event_type: str, payload: dict[str, Any]) -> str:
            return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        session: AgentSession
        try:
            session = await self.agent_service.resolve_and_authorize_context(
                user_id=user.id,
                project_id=request.project_id,
                repository_id=request.repository_id,
                branch_id=request.branch_id,
                session_id=request.session_id,
            )
        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            yield _format_sse("agent.error", {"error": sanitized, "status_code": 400})
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
                "phase": "planning",
            },
        )

        initial_state = create_initial_state(
            user_query=request.message,
            repository_id=str(session.repository_id),
            branch_id=str(session.branch_id) if session.branch_id else None,
            project_id=str(session.project_id),
            user_id=str(user.id),
            metadata={"session_id": str(session.id), "phase": "planning"},
        )

        graph = build_agent_graph(
            model_provider=model_provider_override,
            db_session=self.db,
            user_id=user.id,
            system_prompt=PLANNING_AGENT_SYSTEM_PROMPT,
        )

        accumulated_retrieved_context: list[dict[str, Any]] = []
        accumulated_tool_results: list[dict[str, Any]] = []
        final_answer: str = ""
        iteration_count: int = 1

        try:
            stream_gen = graph.astream(initial_state, stream_mode="updates")

            async for update in stream_gen:
                if not isinstance(update, dict):
                    continue

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

                if "tools" in update:
                    tools_update = update["tools"]
                    new_tools = tools_update.get("tool_results", [])
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

        except Exception as exc:
            sanitized = sanitize_secret_text(str(exc))
            logger.error(f"[PlanningService:stream_plan] Error: {sanitized}")
            yield _format_sse("agent.error", {"error": sanitized, "status_code": 500})
            return

        # Synthesize plan & approval
        sources = self.agent_service._extract_deduplicated_sources(accumulated_retrieved_context)
        plan_dict = self._parse_plan_json(final_answer, default_summary=f"Plan for: {request.message[:80]}")

        parsed_affected_files: list[AffectedFile] = []
        for af_data in plan_dict.get("affected_files", []):
            if isinstance(af_data, dict):
                ct_val = af_data.get("change_type", "MODIFY")
                try:
                    ct = ChangeType(str(ct_val).upper())
                except ValueError:
                    ct = ChangeType.MODIFY
                parsed_affected_files.append(
                    AffectedFile(
                        file_path=str(af_data.get("file_path", "")),
                        change_type=ct,
                        reason=str(af_data.get("reason", "Required modification.")),
                        symbols=[str(s) for s in af_data.get("symbols", [])],
                    )
                )

        plan = ImplementationPlan(
            summary=plan_dict.get("summary", "Implementation Plan"),
            problem_statement=plan_dict.get("problem_statement", request.message),
            approach=plan_dict.get("approach", "Follow architectural best practices."),
            affected_files=parsed_affected_files,
            new_files=[str(f) for f in plan_dict.get("new_files", [])],
            deleted_files=[str(f) for f in plan_dict.get("deleted_files", [])],
            symbols=[str(s) for s in plan_dict.get("symbols", [])],
            test_strategy=plan_dict.get("test_strategy", "Execute regression test suite."),
            risks=[str(r) for r in plan_dict.get("risks", [])],
            evidence=sources,
        )

        validated_plan = validate_implementation_plan(plan, require_evidence=False)

        approval = AgentApproval(
            id=uuid.uuid4(),
            session_id=session.id,
            workspace_id=None,
            user_id=user.id,
            approval_type=ApprovalType.PLAN.value,
            status=ApprovalStatus.PENDING.value,
            plan_payload=validated_plan.model_dump(mode="json"),
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)

        plan_event_payload = {
            "session_id": str(session.id),
            "project_id": str(session.project_id),
            "repository_id": str(session.repository_id),
            "branch_id": str(session.branch_id) if session.branch_id else None,
            "plan": validated_plan.model_dump(mode="json"),
            "approval_id": str(approval.id),
            "approval_status": approval.status,
            "created_at": approval.created_at.isoformat(),
        }

        yield _format_sse("agent.plan.created", plan_event_payload)
        yield _format_sse(
            "agent.approval.required",
            {
                "approval_id": str(approval.id),
                "approval_type": "PLAN",
                "session_id": str(session.id),
                "status": "PENDING",
            },
        )

    @staticmethod
    def _to_approval_response(approval: AgentApproval) -> AgentApprovalResponse:
        plan_obj: ImplementationPlan | None = None
        if approval.plan_payload and isinstance(approval.plan_payload, dict):
            try:
                plan_obj = ImplementationPlan.model_validate(approval.plan_payload)
            except Exception:
                pass

        return AgentApprovalResponse(
            approval_id=approval.id,
            session_id=approval.session_id,
            user_id=approval.user_id,
            approval_type=approval.approval_type,
            status=approval.status,
            workspace_id=approval.workspace_id,
            plan=plan_obj,
            created_at=approval.created_at,
            resolved_at=approval.resolved_at,
        )


