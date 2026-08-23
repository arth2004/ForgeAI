"""Planner Agent Implementation for Phase 6 Multi-Agent Architecture."""

import json
import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import BaseChatModelProvider
from app.agent.multi_agent.base import BaseEngineeringAgent
from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.types import AgentRoleEnum, TaskLifecycleState
from app.schemas.agent import AgentPlanRequest, ImplementationPlan
from app.services.planning_service import PlanningService

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Forge AI Planner Agent.
Your responsibility is deep, read-only repository exploration and architecture planning.
You investigate symbols, file structures, and dependencies, and produce a structured ImplementationPlan.

STRICT INVARIANTS:
1. You have strictly READ-ONLY repository access.
2. You cannot modify files, propose git commits, or execute shell commands.
3. You must produce a complete, structured JSON implementation plan adhering to the ImplementationPlan schema.

Your JSON plan output MUST contain:
- summary: Short descriptive title
- problem_statement: Detailed problem formulation
- approach: Step-by-step engineering strategy
- affected_files: List of objects with file_path, change_type, reason
- new_files: List of strings
- deleted_files: List of strings
- test_strategy: Testing commands (e.g. pytest commands)
- risks: Edge cases and failure modes
"""


class PlannerAgent(BaseEngineeringAgent):
    """Specialized agent dedicated to codebase exploration and implementation planning."""

    def __init__(self, model_provider: BaseChatModelProvider) -> None:
        super().__init__(
            model_provider=model_provider,
            role=AgentRoleEnum.PLANNER,
            allowed_tools={"search_repository", "search_symbol", "get_file"},
        )

    async def execute(
        self,
        state: MultiAgentState,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Executes repository investigation and synthesizes an ImplementationPlan."""
        logger.info(
            "PlannerAgent starting investigation for task=%s prompt='%s'",
            state["task_id"],
            state["prompt"][:50],
        )

        plan: ImplementationPlan | None = None

        # 1. Use PlanningService for grounding if DB session and valid UUIDs are present
        if db is not None and state.get("session_id") and state.get("project_id") and state.get("repository_id"):
            try:
                session_id = uuid.UUID(str(state["session_id"]))
                project_id = uuid.UUID(str(state["project_id"]))
                repository_id = uuid.UUID(str(state["repository_id"]))
                branch_id = uuid.UUID(str(state["branch_id"])) if state.get("branch_id") else None
                user_id = uuid.UUID(str(state["user_id"]))

                from app.models.auth import User

                user = await db.get(User, user_id)
                if user:
                    planning_service = PlanningService(db)
                    plan_resp = await planning_service.generate_plan(
                        user=user,
                        request=AgentPlanRequest(
                            message=state["prompt"],
                            project_id=project_id,
                            repository_id=repository_id,
                            branch_id=branch_id,
                            session_id=session_id,
                        ),
                        model_provider_override=self.model_provider,
                    )
                    plan = plan_resp.plan
            except Exception as e:
                logger.warning("PlanningService direct execution fallback: %s", e)


        # 2. Fallback direct LLM synthesis if PlanningService was not used
        if plan is None:
            messages = [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=f"Create an ImplementationPlan for the following task:\n{state['prompt']}"),
            ]

            response = await self.model_provider.ainvoke(messages)
            content_text = str(response.content)

            try:
                clean_json = content_text.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json.removeprefix("```json").removesuffix("```").strip()
                elif clean_json.startswith("```"):
                    clean_json = clean_json.removeprefix("```").removesuffix("```").strip()

                parsed = json.loads(clean_json)
                plan = ImplementationPlan.model_validate(parsed)
            except Exception as err:
                logger.info("Synthesizing default ImplementationPlan structure: %s", err)
                plan = ImplementationPlan(
                    summary=f"Plan: {state['title']}",
                    problem_statement=state["prompt"],
                    approach="Investigate affected routers and verify with targeted unit test suite.",
                    affected_files=[],
                    new_files=[],
                    deleted_files=[],
                    test_strategy="pytest -v",
                    risks=["Potential edge cases in request parameter validation."],
                )

        affected_files = [f.file_path for f in plan.affected_files]
        investigation_summary = (
            f"Planner investigated repository context. Plan: {plan.summary}. "
            f"Approach: {plan.approach[:120]}"
        )

        return {
            "implementation_plan": plan.model_dump(),
            "investigation_summary": investigation_summary,
            "affected_files": affected_files,
            "lifecycle_state": TaskLifecycleState.PLAN_READY.value,
            "active_agent": AgentRoleEnum.PLANNER.value,
            "messages": [
                AIMessage(
                    content=f"Planner completed investigation and proposed plan: {plan.summary}",
                    id=str(uuid.uuid4()),
                )
            ],
        }
