import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.exceptions import AgentExecutionException, ModelProviderException
from app.agent.models import (
    BaseChatModelProvider,
    get_chat_model_provider,
    sanitize_secret_text,
)
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


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

    logger.info(
        f"[AgentGraph] Executing agent node | provider={provider.provider_name} "
        f"model={provider.model_name} message_count={len(messages)}"
    )

    # 2. Invoke Model Provider Abstraction
    try:
        response_msg = await provider.ainvoke(messages)
        content_str = str(response_msg.content)

        logger.info(
            f"[AgentGraph] Agent node completed successfully | "
            f"response_length={len(content_str)}"
        )

        return {
            "messages": [response_msg],
            "final_answer": content_str,
        }

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


def build_agent_graph(
    model_provider: BaseChatModelProvider | None = None,
) -> CompiledStateGraph:
    """Constructs and compiles the minimal Phase 4A LangGraph agent foundation.

    Topology:
        START -> agent_node -> END

    Future Phase 4 iterations can extend this graph by inserting tool decision
    and tool execution nodes between agent and END without rewriting this foundation.
    """
    workflow = StateGraph(AgentState)

    # Define node wrapper supporting injected model provider
    async def _bound_agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await agent_node(state, config, model_provider_override=model_provider)

    workflow.add_node("agent", _bound_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)

    compiled_graph = workflow.compile()
    return compiled_graph
