from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Strongly typed state schema for the Forge AI agent runtime graph.

    Represents the operational context passed across LangGraph nodes.
    """

    user_query: str
    messages: Annotated[list[BaseMessage], add_messages]
    repository_id: str | None
    branch_id: str | None
    retrieved_context: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    final_answer: str | None
    metadata: dict[str, Any]


def create_initial_state(
    user_query: str,
    repository_id: str | None = None,
    branch_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    initial_messages: list[BaseMessage] | None = None,
) -> AgentState:
    """Constructs a validated initial AgentState with standardized defaults."""
    messages: list[BaseMessage]
    if initial_messages is not None:
        messages = list(initial_messages)
    else:
        messages = [HumanMessage(content=user_query)]

    return AgentState(
        user_query=user_query,
        messages=messages,
        repository_id=repository_id,
        branch_id=branch_id,
        retrieved_context=[],
        tool_results=[],
        final_answer=None,
        metadata=metadata or {},
    )
