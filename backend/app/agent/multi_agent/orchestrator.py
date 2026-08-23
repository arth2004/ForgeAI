"""Engineering Orchestrator implementation for Phase 6 Multi-Agent Architecture."""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import BaseChatModelProvider
from app.agent.multi_agent.coder import CoderAgent
from app.agent.multi_agent.config import multi_agent_guards
from app.agent.multi_agent.planner import PlannerAgent
from app.agent.multi_agent.reviewer import ReviewerAgent
from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.tester import TesterAgent
from app.agent.multi_agent.types import TaskLifecycleState

logger = logging.getLogger(__name__)


class EngineeringOrchestrator:
    """Central supervisor coordinating specialized engineering subagents in a bounded workflow."""

    def __init__(
        self,
        planner_provider: BaseChatModelProvider,
        coder_provider: BaseChatModelProvider,
        tester_provider: BaseChatModelProvider,
        reviewer_provider: BaseChatModelProvider,
        db: AsyncSession | None = None,
    ) -> None:
        self.db = db
        self.planner = PlannerAgent(model_provider=planner_provider)
        self.coder = CoderAgent(model_provider=coder_provider)
        self.tester = TesterAgent(model_provider=tester_provider)
        self.reviewer = ReviewerAgent(model_provider=reviewer_provider)

        self._graph = self._build_workflow_graph()

    def _build_workflow_graph(self) -> CompiledStateGraph:
        """Constructs the centralized LangGraph supervisor StateGraph."""
        builder = StateGraph(MultiAgentState)

        # 1. Register subagent nodes
        builder.add_node("planner_node", self._run_planner)
        builder.add_node("coder_node", self._run_coder)
        builder.add_node("tester_node", self._run_tester)
        builder.add_node("reviewer_node", self._run_reviewer)
        builder.add_node("supervisor_guard_node", self._run_guard)

        # 2. Add edges
        builder.add_edge(START, "supervisor_guard_node")

        # Dynamic routing from supervisor
        builder.add_conditional_edges(
            "supervisor_guard_node",
            self._route_next_step,
            {
                "planner": "planner_node",
                "coder": "coder_node",
                "tester": "tester_node",
                "reviewer": "reviewer_node",
                "end": END,
            },
        )

        builder.add_edge("planner_node", "supervisor_guard_node")
        builder.add_edge("coder_node", "supervisor_guard_node")
        builder.add_edge("tester_node", "supervisor_guard_node")
        builder.add_edge("reviewer_node", "supervisor_guard_node")

        return builder.compile()

    # --- Node Execution Handlers ---

    async def _run_guard(self, state: MultiAgentState) -> dict[str, Any]:
        """Supervisor node tracking iterations and enforcing execution guardrails."""
        current_iter = state.get("iteration_count", 0) + 1

        # Check hard bounds
        if current_iter > multi_agent_guards.MAX_TOTAL_WORKFLOW_ITERATIONS:
            logger.warning("Task %s reached MAX_TOTAL_WORKFLOW_ITERATIONS (%s)", state["task_id"], current_iter)
            return {
                "iteration_count": current_iter,
                "lifecycle_state": TaskLifecycleState.WAITING_HUMAN_INTERVENTION.value,
                "failure_reason": f"Execution iteration ceiling reached ({multi_agent_guards.MAX_TOTAL_WORKFLOW_ITERATIONS}). Human review required.",
            }

        return {"iteration_count": current_iter}

    async def _run_planner(self, state: MultiAgentState) -> dict[str, Any]:
        """Dispatches execution to PlannerAgent."""
        return await self.planner.execute(state=state, db=self.db)

    async def _run_coder(self, state: MultiAgentState) -> dict[str, Any]:
        """Dispatches execution to CoderAgent."""
        return await self.coder.execute(state=state, db=self.db)

    async def _run_tester(self, state: MultiAgentState) -> dict[str, Any]:
        """Dispatches execution to TesterAgent."""
        return await self.tester.execute(state=state, db=self.db)

    async def _run_reviewer(self, state: MultiAgentState) -> dict[str, Any]:
        """Dispatches execution to ReviewerAgent."""
        return await self.reviewer.execute(state=state, db=self.db)

    # --- Routing & Control Logic ---

    def _route_next_step(self, state: MultiAgentState) -> str:
        """Evaluates lifecycle state and routes deterministically to the next subagent."""
        lifecycle = state.get("lifecycle_state", TaskLifecycleState.TASK_CREATED.value)
        test_repair_count = state.get("test_repair_count", 0)
        review_iteration_count = state.get("review_iteration_count", 0)

        # Terminal & Approval Pause States
        if lifecycle in [
            TaskLifecycleState.COMPLETED.value,
            TaskLifecycleState.FAILED.value,
            TaskLifecycleState.CANCELLED.value,
            TaskLifecycleState.WAITING_HUMAN_INTERVENTION.value,
            TaskLifecycleState.WAITING_PLAN_APPROVAL.value,
            TaskLifecycleState.WAITING_DIFF_APPROVAL.value,
            TaskLifecycleState.WAITING_COMMIT_APPROVAL.value,
            TaskLifecycleState.WAITING_PUSH_APPROVAL.value,
            TaskLifecycleState.WAITING_PR_APPROVAL.value,
        ]:
            return "end"

        # 1. Starting -> Planner
        if lifecycle in [TaskLifecycleState.TASK_CREATED.value, TaskLifecycleState.PLANNING.value]:
            return "planner"

        # 2. Plan ready -> Pause at Gate 1 or proceed if approved
        if lifecycle == TaskLifecycleState.PLAN_READY.value:
            if state.get("approval_status", {}).get("PLAN") != "APPROVED":
                return "end"
            return "coder"

        # 3. Workspace Ready / Implementing -> Coder
        if lifecycle in [TaskLifecycleState.WORKSPACE_READY.value, TaskLifecycleState.IMPLEMENTING.value]:
            return "coder"

        # 4. Patch Ready -> Pause at Gate 2 or proceed if approved
        if lifecycle == TaskLifecycleState.PATCH_READY.value:
            if state.get("approval_status", {}).get("DIFF") != "APPROVED":
                return "end"
            return "tester"

        # 5. Testing logic & repair loop
        if lifecycle == TaskLifecycleState.TESTING.value:
            return "tester"

        if lifecycle == TaskLifecycleState.TEST_FAILED.value:
            if test_repair_count < multi_agent_guards.MAX_TEST_REPAIR_LOOPS:
                return "coder"
            return "end"

        if lifecycle == TaskLifecycleState.TEST_PASSED.value:
            return "reviewer"

        # 6. Review logic & repair loop
        if lifecycle == TaskLifecycleState.REVIEWING.value:
            return "reviewer"

        if lifecycle == TaskLifecycleState.REVIEW_FAILED.value:
            if review_iteration_count < multi_agent_guards.MAX_REVIEW_ITERATIONS:
                return "coder"
            return "end"

        if lifecycle == TaskLifecycleState.REVIEW_PASSED.value:
            return "end"

        return "end"

    async def ainvoke(self, state: MultiAgentState) -> MultiAgentState:
        """Executes the compiled multi-agent state graph asynchronously."""
        from typing import cast

        res = await self._graph.ainvoke(state)
        return cast(MultiAgentState, res)

