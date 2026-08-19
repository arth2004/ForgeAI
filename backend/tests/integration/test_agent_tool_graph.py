from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_agent_graph
from app.agent.models import MockChatModelProvider
from app.agent.state import create_initial_state
from app.models.auth import User


@pytest.mark.asyncio
async def test_agent_graph_scenario_1_search_repository_tool_flow(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario 1: Model requests search_repository, receives evidence, and produces a final answer."""
    project = indexed_tool_repo["project"]

    # Turn 1: Model requests search_repository
    # Turn 2: Model synthesizes final answer after receiving evidence
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_repository",
                "args": {
                    "query": "Where are embeddings generated?",
                    "project_id": str(project.id),
                    "top_k": 3,
                },
                "id": "call_search_1",
            }
        ],
    )
    final_answer_msg = AIMessage(
        content="Embeddings are generated in backend/app/services/embedding/gemini.py by GeminiEmbeddingProvider."
    )

    mock_provider = MockChatModelProvider(responses=[tool_call_msg, final_answer_msg])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Where are embeddings generated?",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    query_vec = [0.0] * 768
    query_vec[0] = 1.0

    with patch(
        "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
        new_callable=AsyncMock,
        return_value=query_vec,
    ):
        result_state = await graph.ainvoke(initial_state)

    # 1. Verify message sequence: Human -> AI(tool_calls) -> ToolMessage -> AI(final)
    messages = result_state.get("messages", [])
    assert len(messages) == 4
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls is not None and len(messages[1].tool_calls) == 1
    assert isinstance(messages[2], ToolMessage)
    assert messages[2].tool_call_id == "call_search_1"
    assert isinstance(messages[3], AIMessage)
    assert messages[3].content == final_answer_msg.content

    # 2. Verify final_answer and context
    assert result_state.get("final_answer") == final_answer_msg.content
    assert len(result_state.get("tool_results", [])) == 1
    assert result_state["tool_results"][0]["tool"] == "search_repository"
    assert result_state["tool_results"][0]["success"] is True
    assert len(result_state.get("retrieved_context", [])) > 0


@pytest.mark.asyncio
async def test_agent_graph_scenario_2_symbol_and_file_tool_flow(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario 2: Model requests search_symbol, inspects file, and returns final answer."""
    project = indexed_tool_repo["project"]

    tool_call_sym = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "HybridSearchEngine",
                    "project_id": str(project.id),
                },
                "id": "call_sym_1",
            }
        ],
    )
    final_resp = AIMessage(
        content="HybridSearchEngine is defined in backend/app/services/retrieval/hybrid.py at line 15."
    )

    mock_provider = MockChatModelProvider(responses=[tool_call_sym, final_resp])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Find HybridSearchEngine symbol",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    assert result_state.get("final_answer") == final_resp.content
    assert len(result_state.get("tool_results", [])) == 1
    assert result_state["tool_results"][0]["tool"] == "search_symbol"
    assert result_state["tool_results"][0]["success"] is True


@pytest.mark.asyncio
async def test_agent_graph_scenario_3_direct_answer_no_tools(
    db_session: AsyncSession, test_user: User
):
    """Scenario 3: Model responds directly without requesting any tools."""
    direct_msg = AIMessage(content="Hello! I am Forge AI, ready to assist with your codebase.")

    mock_provider = MockChatModelProvider(responses=[direct_msg])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(user_query="Hello")
    result_state = await graph.ainvoke(initial_state)

    assert result_state.get("final_answer") == direct_msg.content
    assert len(result_state.get("tool_results", [])) == 0
    assert len(result_state.get("messages", [])) == 2


@pytest.mark.asyncio
async def test_agent_graph_scenario_4_tool_error_recovery(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario 4: Tool execution returns an error and model recovers cleanly."""
    project = indexed_tool_repo["project"]

    tool_call_bad = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_file",
                "args": {
                    "file_path": "missing_file.py",
                    "project_id": str(project.id),
                },
                "id": "call_bad_1",
            }
        ],
    )
    recovered_answer = AIMessage(
        content="I searched for missing_file.py but it does not exist in the active index."
    )

    mock_provider = MockChatModelProvider(responses=[tool_call_bad, recovered_answer])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Read missing_file.py",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    assert result_state.get("final_answer") == recovered_answer.content
    assert len(result_state.get("tool_results", [])) == 1
    assert result_state["tool_results"][0]["success"] is False
    assert "not found" in result_state["tool_results"][0]["error"]


@pytest.mark.asyncio
async def test_agent_graph_scenario_5_max_iterations_guard(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario 5: Ensures infinite tool request loops are bounded by MAX_AGENT_ITERATIONS."""
    project = indexed_tool_repo["project"]

    # Endless tool call requests
    endless_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "test",
                    "project_id": str(project.id),
                },
                "id": "call_loop",
            }
        ],
    )

    from app.agent.tools.limits import ToolUsageGuard

    # Provider will keep requesting tools on every invocation
    mock_provider = MockChatModelProvider(responses=[endless_tool_call] * 10)
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
        tool_guard=ToolUsageGuard(max_total_calls=50, max_per_tool_calls={"search_symbol": 50}),
    )

    initial_state = create_initial_state(
        user_query="Loop test",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    # Verify iteration count reached limit and graph halted at END
    assert result_state.get("iteration_count", 0) >= 5
