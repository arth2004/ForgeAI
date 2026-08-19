import json
import logging
import uuid
from typing import Any, Literal

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import AgentExecutionException, ModelProviderException
from app.agent.models import (
    BaseChatModelProvider,
    get_chat_model_provider,
    sanitize_secret_text,
)
from app.agent.state import AgentState
from app.agent.tools import (
    ToolUsageGuard,
    get_agent_tool_by_name,
)
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS: int = 5


async def agent_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    model_provider_override: BaseChatModelProvider | None = None,
) -> dict[str, Any]:
    """Core Agent reasoning node in the LangGraph graph.

    Processes incoming user query / conversation messages, invokes the configured
    LLM abstraction, and updates the agent state with the response.
    """
    # 1. Resolve model provider instance
    provider: BaseChatModelProvider
    if model_provider_override is not None:
        provider = model_provider_override
    elif config and "configurable" in config and "model_provider" in config["configurable"]:
        provider = config["configurable"]["model_provider"]
    else:
        provider = get_chat_model_provider()

    user_q = state.get("user_query", "")
    messages: list[BaseMessage] = state.get("messages", [])

    if not messages and user_q:
        messages = [HumanMessage(content=user_q)]

    current_iter = state.get("iteration_count", 0) + 1

    logger.info(
        f"[AgentGraph] Executing agent node | iteration={current_iter} provider={provider.provider_name} "
        f"model={provider.model_name} message_count={len(messages)}"
    )

    # 2. Invoke Model Provider Abstraction
    try:
        response_msg = await provider.ainvoke(messages)
        content_str = str(response_msg.content)
        has_tools = bool(getattr(response_msg, "tool_calls", None))

        logger.info(
            f"[AgentGraph] Agent node completed successfully | "
            f"has_tool_calls={has_tools} response_length={len(content_str)}"
        )

        state_update: dict[str, Any] = {
            "messages": [response_msg],
            "iteration_count": current_iter,
        }

        # If model did not request tool calls, treat as final answer
        if not has_tools:
            state_update["final_answer"] = content_str

        return state_update

    except ModelProviderException as mpe:
        sanitized_msg = sanitize_secret_text(mpe.message)
        logger.error(f"[AgentGraph] Model provider error in agent node: {sanitized_msg}")
        raise AgentExecutionException(
            message=f"Agent model invocation failed: {sanitized_msg}",
            node_name="agent",
            details=mpe.details,
        ) from mpe
    except Exception as exc:
        sanitized_exc = sanitize_secret_text(str(exc))
        logger.error(f"[AgentGraph] Unexpected error during agent node execution: {sanitized_exc}")
        raise AgentExecutionException(
            message=f"Agent execution encountered an unexpected error: {sanitized_exc}",
            node_name="agent",
        ) from exc


def tool_router(state: AgentState) -> Literal["tools", "__end__"]:
    """Determines whether the model requested tool execution or produced a final answer."""
    messages = state.get("messages", [])
    if not messages:
        return "__end__"

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None)

    current_iter = state.get("iteration_count", 0)
    if current_iter >= MAX_AGENT_ITERATIONS:
        logger.warning(
            f"[AgentGraph] Reached maximum tool iteration limit ({MAX_AGENT_ITERATIONS}). Halting graph."
        )
        return "__end__"

    if tool_calls and len(tool_calls) > 0:
        return "tools"

    return "__end__"


async def tools_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    db_session_override: AsyncSession | None = None,
    user_id_override: uuid.UUID | None = None,
    tool_guard_override: ToolUsageGuard | None = None,
) -> dict[str, Any]:
    """Executes requested tool calls against the Phase 3 repository intelligence services."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", []) or []
    if not tool_calls:
        return {}

    guard = tool_guard_override if tool_guard_override is not None else ToolUsageGuard()

    # Determine user context for authorization
    user_uuid: uuid.UUID
    if user_id_override:
        user_uuid = user_id_override
    elif state.get("user_id"):
        try:
            user_uuid = uuid.UUID(str(state["user_id"]))
        except ValueError:
            user_uuid = uuid.uuid4()
    elif config and "configurable" in config and "user_id" in config["configurable"]:
        user_uuid = config["configurable"]["user_id"]
    else:
        user_uuid = uuid.uuid4()

    tool_messages: list[BaseMessage] = []
    executed_results: list[dict[str, Any]] = list(state.get("tool_results", []))
    new_retrieved_context: list[dict[str, Any]] = []

    async def _execute_single_tool(session: AsyncSession, tc: dict[str, Any]) -> None:
        tool_name = tc.get("name", "")
        call_id = tc.get("id", str(uuid.uuid4()))
        tool_args = dict(tc.get("args", {}))

        # Inject default project_id/repository_id/branch_id from state if not passed by LLM
        if "project_id" not in tool_args and state.get("project_id"):
            tool_args["project_id"] = state["project_id"]
        if "repository_id" not in tool_args and state.get("repository_id"):
            tool_args["repository_id"] = state["repository_id"]
        if "branch_id" not in tool_args and state.get("branch_id"):
            tool_args["branch_id"] = state["branch_id"]

        tool = get_agent_tool_by_name(tool_name)
        if not tool:
            err_msg = f"Tool '{tool_name}' is not registered."
            logger.warning(f"[AgentGraph:tools_node] {err_msg}")
            tool_messages.append(ToolMessage(content=json.dumps({"error": err_msg}), tool_call_id=call_id))
            executed_results.append({"tool": tool_name, "success": False, "error": err_msg})
            return

        try:
            guard.record_call(tool_name)
            res = await tool.aexecute(db=session, user_id=user_uuid, **tool_args)

            tool_messages.append(ToolMessage(content=json.dumps(res.model_dump()), tool_call_id=call_id))
            executed_results.append({"tool": tool_name, "success": res.success, "data": res.data, "error": res.error})

            if res.success and isinstance(res.data, dict) and "results" in res.data:
                new_retrieved_context.extend(res.data["results"])

        except Exception as exc:
            sanitized_err = sanitize_secret_text(str(exc))
            logger.error(f"[AgentGraph:tools_node] Error executing tool '{tool_name}': {sanitized_err}")
            tool_messages.append(
                ToolMessage(content=json.dumps({"error": sanitized_err, "tool_name": tool_name}), tool_call_id=call_id)
            )
            executed_results.append({"tool": tool_name, "success": False, "error": sanitized_err})

    if db_session_override is not None:
        for tc in tool_calls:
            await _execute_single_tool(db_session_override, tc)
    else:
        async with AsyncSessionLocal() as session:
            for tc in tool_calls:
                await _execute_single_tool(session, tc)

    return {
        "messages": tool_messages,
        "tool_results": executed_results,
        "retrieved_context": list(state.get("retrieved_context", [])) + new_retrieved_context,
        "iteration_count": state.get("iteration_count", 0),
    }


def build_agent_graph(
    model_provider: BaseChatModelProvider | None = None,
    db_session: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    tool_guard: ToolUsageGuard | None = None,
) -> CompiledStateGraph:
    """Constructs and compiles the Phase 4B LangGraph agent graph with repository tool node.

    Topology:
        START -> agent_node -> tool_router
                                  ├── "tools" -> tools_node -> agent_node
                                  └── "__end__" -> END
    """
    workflow = StateGraph(AgentState)
    active_guard = tool_guard if tool_guard is not None else ToolUsageGuard()

    # Bound Agent Node
    async def _bound_agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await agent_node(state, config, model_provider_override=model_provider)

    # Bound Tools Node
    async def _bound_tools_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await tools_node(
            state,
            config,
            db_session_override=db_session,
            user_id_override=user_id,
            tool_guard_override=active_guard,
        )

    workflow.add_node("agent", _bound_agent_node)
    workflow.add_node("tools", _bound_tools_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tool_router, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    compiled_graph = workflow.compile()
    return compiled_graph
