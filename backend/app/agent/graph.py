import json
import logging
import time
import uuid
from typing import Any, Literal

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
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
from app.agent.prompts import DEFAULT_AGENT_SYSTEM_PROMPT
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
    system_prompt_override: str | None = None,
) -> dict[str, Any]:
    """Core Agent reasoning node in the LangGraph graph.

    Processes incoming user query / conversation messages, injects system reasoning
    instructions if needed, invokes the configured LLM abstraction, and updates state.
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
    messages: list[BaseMessage] = list(state.get("messages", []))

    # Ensure HumanMessage exists for the query if messages are empty
    if not messages and user_q:
        messages = [HumanMessage(content=user_q)]

    # Prepend reasoning system instructions if not already present
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    if not has_system:
        configured_prompt = (
            system_prompt_override
            or (config.get("configurable", {}).get("system_prompt") if config else None)
            or DEFAULT_AGENT_SYSTEM_PROMPT
        )
        messages = [SystemMessage(content=configured_prompt)] + messages

    current_iter = state.get("iteration_count", 0) + 1

    if current_iter == 1:
        logger.info(
            f"[agent.execution.started] provider={provider.provider_name} "
            f"model={provider.model_name} query_length={len(user_q)} message_count={len(messages)}"
        )
    else:
        logger.info(
            f"[agent.reasoning.step] iteration={current_iter} provider={provider.provider_name} "
            f"model={provider.model_name} message_count={len(messages)}"
        )

    # 2. Invoke Model Provider Abstraction
    start_time = time.perf_counter()
    try:
        response_msg = await provider.ainvoke(messages)
        content_str = str(response_msg.content)
        tool_calls = getattr(response_msg, "tool_calls", None) or []
        has_tools = len(tool_calls) > 0
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if has_tools:
            for tc in tool_calls:
                tc_name = tc.get("name", "unknown")
                tc_id = tc.get("id", "unknown")
                logger.info(
                    f"[agent.tool.requested] tool={tc_name} call_id={tc_id} "
                    f"iteration={current_iter} duration_ms={duration_ms}"
                )
        else:
            retrieved_count = len(state.get("retrieved_context", []))
            logger.info(
                f"[agent.execution.completed] iteration={current_iter} duration_ms={duration_ms} "
                f"response_length={len(content_str)} retrieved_context_count={retrieved_count}"
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
        logger.error(f"[agent.model.failed] error={sanitized_msg} iteration={current_iter}")
        raise AgentExecutionException(
            message=f"Agent model invocation failed: {sanitized_msg}",
            node_name="agent",
            details=mpe.details,
        ) from mpe
    except Exception as exc:
        sanitized_exc = sanitize_secret_text(str(exc))
        logger.error(f"[agent.unexpected.failed] error={sanitized_exc} iteration={current_iter}")
        raise AgentExecutionException(
            message=f"Agent execution encountered an unexpected error: {sanitized_exc}",
            node_name="agent",
        ) from exc


def tool_router(
    state: AgentState,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> Literal["tools", "__end__"]:
    """Determines whether the model requested tool execution or produced a final answer."""
    messages = state.get("messages", [])
    if not messages:
        return "__end__"

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None)

    current_iter = state.get("iteration_count", 0)
    if current_iter >= max_iterations:
        logger.warning(
            f"[agent.execution.limit_reached] Reached maximum tool iteration limit ({max_iterations}). Halting graph."
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
            logger.warning(f"[agent.tool.failed] tool={tool_name} call_id={call_id} error={err_msg}")
            tool_messages.append(ToolMessage(content=json.dumps({"error": err_msg}), tool_call_id=call_id))
            executed_results.append({"tool": tool_name, "success": False, "error": err_msg})
            return

        start_tool_time = time.perf_counter()
        try:
            guard.record_call(tool_name)
            res = await tool.aexecute(db=session, user_id=user_uuid, **tool_args)
            tool_duration_ms = round((time.perf_counter() - start_tool_time) * 1000, 2)

            tool_messages.append(ToolMessage(content=json.dumps(res.model_dump()), tool_call_id=call_id))
            executed_results.append({
                "tool": tool_name,
                "success": res.success,
                "data": res.data,
                "error": res.error,
                "duration_ms": tool_duration_ms,
            })

            if res.success and isinstance(res.data, dict):
                logger.info(
                    f"[agent.tool.completed] tool={tool_name} call_id={call_id} "
                    f"duration_ms={tool_duration_ms} success=True"
                )
                if "results" in res.data and isinstance(res.data["results"], list):
                    new_retrieved_context.extend(res.data["results"])
                elif "symbols" in res.data and isinstance(res.data["symbols"], list):
                    new_retrieved_context.extend(res.data["symbols"])
                elif "file_path" in res.data:
                    new_retrieved_context.append({
                        "file_path": res.data.get("file_path"),
                        "content": res.data.get("content"),
                        "line_range": res.data.get("line_range"),
                    })
            else:
                logger.warning(
                    f"[agent.tool.completed] tool={tool_name} call_id={call_id} "
                    f"duration_ms={tool_duration_ms} success=False error={res.error}"
                )

        except Exception as exc:
            tool_duration_ms = round((time.perf_counter() - start_tool_time) * 1000, 2)
            sanitized_err = sanitize_secret_text(str(exc))
            logger.warning(
                f"[agent.tool.failed] tool={tool_name} call_id={call_id} "
                f"duration_ms={tool_duration_ms} error={sanitized_err}"
            )
            tool_messages.append(
                ToolMessage(content=json.dumps({"error": sanitized_err, "tool_name": tool_name}), tool_call_id=call_id)
            )
            executed_results.append({
                "tool": tool_name,
                "success": False,
                "error": sanitized_err,
                "duration_ms": tool_duration_ms,
            })

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
    max_iterations: int = MAX_AGENT_ITERATIONS,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Constructs and compiles the Phase 4 LangGraph agent graph with repository reasoning loop.

    Topology:
        START -> agent_node -> tool_router
                                  ├── "tools" -> tools_node -> agent_node
                                  └── "__end__" -> END
    """
    workflow = StateGraph(AgentState)
    active_guard = tool_guard if tool_guard is not None else ToolUsageGuard()

    # Bound Agent Node
    async def _bound_agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await agent_node(
            state,
            config,
            model_provider_override=model_provider,
            system_prompt_override=system_prompt,
        )

    # Bound Tools Node
    async def _bound_tools_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await tools_node(
            state,
            config,
            db_session_override=db_session,
            user_id_override=user_id,
            tool_guard_override=active_guard,
        )

    # Bound Tool Router
    def _bound_tool_router(state: AgentState) -> Literal["tools", "__end__"]:
        return tool_router(state, max_iterations=max_iterations)

    workflow.add_node("agent", _bound_agent_node)
    workflow.add_node("tools", _bound_tools_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", _bound_tool_router, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    compiled_graph = workflow.compile()
    return compiled_graph
