import logging
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_agent_graph
from app.agent.models import MockChatModelProvider
from app.agent.prompts import DEFAULT_AGENT_SYSTEM_PROMPT
from app.agent.state import create_initial_state
from app.agent.tools.limits import ToolUsageGuard
from app.models.auth import User


@pytest.mark.asyncio
async def test_agent_reasoning_direct_answer_no_tools(
    db_session: AsyncSession, test_user: User
):
    """Scenario A: General question answered directly by the agent without any tool calls."""
    direct_answer = AIMessage(
        content="Forge AI is a repository intelligence and code reasoning engine."
    )
    mock_provider = MockChatModelProvider(responses=[direct_answer])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(user_query="What is Forge AI?")
    result_state = await graph.ainvoke(initial_state)

    # 1. Verify single iteration and direct response
    assert result_state.get("iteration_count") == 1
    assert result_state.get("final_answer") == direct_answer.content
    assert len(result_state.get("tool_results", [])) == 0
    assert len(result_state.get("retrieved_context", [])) == 0

    # 2. Verify messages: HumanMessage + AIMessage in state, and SystemMessage in LLM call
    messages = result_state.get("messages", [])
    assert len(messages) == 2
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "What is Forge AI?"
    assert isinstance(messages[1], AIMessage)

    # Verify model provider received the SystemMessage
    llm_history = mock_provider.call_history[0]
    assert len(llm_history) == 2
    assert isinstance(llm_history[0], SystemMessage)
    assert llm_history[0].content == DEFAULT_AGENT_SYSTEM_PROMPT
    assert isinstance(llm_history[1], HumanMessage)


@pytest.mark.asyncio
async def test_agent_reasoning_single_step_tool_selection_and_grounding(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario B: Repository question requiring search_repository, followed by grounded response."""
    project = indexed_tool_repo["project"]

    # Step 1: Model requests search_repository
    step1_search = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_repository",
                "args": {
                    "query": "Where are embeddings generated?",
                    "project_id": str(project.id),
                    "top_k": 3,
                },
                "id": "call_embed_search",
            }
        ],
    )
    # Step 2: Model synthesizes grounded answer citing retrieved files
    step2_answer = AIMessage(
        content="Embeddings are generated in `backend/app/services/embedding/gemini.py` by `GeminiEmbeddingProvider`."
    )

    mock_provider = MockChatModelProvider(responses=[step1_search, step2_answer])
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

    assert result_state.get("iteration_count") == 2
    assert result_state.get("final_answer") == step2_answer.content
    assert len(result_state.get("tool_results", [])) == 1
    assert result_state["tool_results"][0]["tool"] == "search_repository"
    assert result_state["tool_results"][0]["success"] is True

    # Verify retrieved context was populated
    retrieved = result_state.get("retrieved_context", [])
    assert len(retrieved) > 0
    assert any("gemini.py" in str(item.get("file_path")) for item in retrieved)


@pytest.mark.asyncio
async def test_agent_reasoning_multi_step_investigation_and_evidence_accumulation(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario C: Multi-step investigation combining search_repository -> search_symbol -> get_file."""
    project = indexed_tool_repo["project"]

    # Step 1: Broad search for retrieval engine
    step1_search = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_repository",
                "args": {
                    "query": "Where is hybrid retrieval implemented?",
                    "project_id": str(project.id),
                },
                "id": "call_step1",
            }
        ],
    )
    # Step 2: Search specific symbol found in initial search
    step2_symbol = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "HybridSearchEngine",
                    "project_id": str(project.id),
                },
                "id": "call_step2",
            }
        ],
    )
    # Step 3: Inspect file implementation lines
    step3_file = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_file",
                "args": {
                    "file_path": "backend/app/services/retrieval/hybrid.py",
                    "project_id": str(project.id),
                    "start_line": 15,
                    "end_line": 60,
                },
                "id": "call_step3",
            }
        ],
    )
    # Step 4: Final synthesized grounded answer
    step4_answer = AIMessage(
        content=(
            "Hybrid retrieval is implemented in `backend/app/services/retrieval/hybrid.py`. "
            "The `HybridSearchEngine` class coordinates dense vector similarity and sparse keyword ranking."
        )
    )

    mock_provider = MockChatModelProvider(
        responses=[step1_search, step2_symbol, step3_file, step4_answer]
    )
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Explain the hybrid retrieval implementation in detail.",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    query_vec = [0.0] * 768
    query_vec[3] = 1.0

    with patch(
        "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
        new_callable=AsyncMock,
        return_value=query_vec,
    ):
        result_state = await graph.ainvoke(initial_state)

    # 1. Verify 4 iterations completed
    assert result_state.get("iteration_count") == 4
    assert result_state.get("final_answer") == step4_answer.content

    # 2. Verify all 3 tool results were executed in order
    tool_results = result_state.get("tool_results", [])
    assert len(tool_results) == 3
    assert tool_results[0]["tool"] == "search_repository"
    assert tool_results[1]["tool"] == "search_symbol"
    assert tool_results[2]["tool"] == "get_file"

    # 3. Verify evidence accumulation: context contains items from all 3 tools
    accumulated_context = result_state.get("retrieved_context", [])
    assert len(accumulated_context) >= 3
    file_paths = [str(ctx.get("file_path", "")) for ctx in accumulated_context]
    assert any("hybrid.py" in fp for fp in file_paths)


@pytest.mark.asyncio
async def test_agent_reasoning_no_hallucination_on_missing_component(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario D: Non-existent component query returns empty evidence and model reports absence without hallucinating."""
    project = indexed_tool_repo["project"]

    step1_search = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_repository",
                "args": {
                    "query": "Stripe billing and subscription webhook handler",
                    "project_id": str(project.id),
                },
                "id": "call_missing_search",
            }
        ],
    )
    step2_honest_answer = AIMessage(
        content=(
            "Based on the repository index, there is no Stripe billing or subscription webhook handler implemented in this project."
        )
    )

    mock_provider = MockChatModelProvider(responses=[step1_search, step2_honest_answer])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Where is the Stripe webhook handled?",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    query_vec = [0.0] * 768

    with patch(
        "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
        new_callable=AsyncMock,
        return_value=query_vec,
    ):
        result_state = await graph.ainvoke(initial_state)

    assert result_state.get("iteration_count") == 2
    assert "no Stripe billing" in str(result_state.get("final_answer"))
    assert result_state["tool_results"][0]["success"] is True


@pytest.mark.asyncio
async def test_agent_reasoning_tool_failure_recovery_and_alternate_tool(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario E: Tool failure recovery where model handles a missing file error and falls back gracefully."""
    project = indexed_tool_repo["project"]

    # Step 1: Model tries to get non-existent file
    step1_bad_file = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_file",
                "args": {
                    "file_path": "backend/app/services/non_existent.py",
                    "project_id": str(project.id),
                },
                "id": "call_bad_file",
            }
        ],
    )
    # Step 2: Model recovers and searches symbols instead
    step2_symbol = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "GeminiEmbeddingProvider",
                    "project_id": str(project.id),
                },
                "id": "call_recovery_symbol",
            }
        ],
    )
    # Step 3: Final grounded answer
    step3_answer = AIMessage(
        content="`non_existent.py` was not found, but `GeminiEmbeddingProvider` was located in `backend/app/services/embedding/gemini.py`."
    )

    mock_provider = MockChatModelProvider(responses=[step1_bad_file, step2_symbol, step3_answer])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Find GeminiEmbeddingProvider",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    assert result_state.get("iteration_count") == 3
    tool_results = result_state.get("tool_results", [])
    assert len(tool_results) == 2
    assert tool_results[0]["success"] is False
    assert tool_results[1]["success"] is True
    assert result_state.get("final_answer") == step3_answer.content


@pytest.mark.asyncio
async def test_agent_reasoning_max_iterations_guard_halts_infinite_loops(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario F: Verifies hard termination when model continuously requests tools up to MAX_AGENT_ITERATIONS."""
    project = indexed_tool_repo["project"]

    endless_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "test",
                    "project_id": str(project.id),
                },
                "id": "call_infinite_loop",
            }
        ],
    )

    # Provider returns endless tool calls for 10 turns
    mock_provider = MockChatModelProvider(responses=[endless_tool_call] * 10)
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
        tool_guard=ToolUsageGuard(max_total_calls=50, max_per_tool_calls={"search_symbol": 50}),
        max_iterations=5,
    )

    initial_state = create_initial_state(
        user_query="Test infinite loop",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    # Must halt at exactly 5 iterations
    assert result_state.get("iteration_count") == 5


@pytest.mark.asyncio
async def test_agent_reasoning_custom_max_iterations_override(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario G: Verifies that max_iterations parameter can be configured to halt earlier (e.g. 3)."""
    project = indexed_tool_repo["project"]

    loop_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "test",
                    "project_id": str(project.id),
                },
                "id": "call_custom_iter",
            }
        ],
    )

    mock_provider = MockChatModelProvider(responses=[loop_call] * 10)
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
        tool_guard=ToolUsageGuard(max_total_calls=50, max_per_tool_calls={"search_symbol": 50}),
        max_iterations=3,
    )

    initial_state = create_initial_state(
        user_query="Test 3 iterations",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)
    assert result_state.get("iteration_count") == 3


@pytest.mark.asyncio
async def test_agent_reasoning_tool_usage_guard_enforcement(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Scenario H: Verifies ToolUsageGuard prevents tool spam and returns structured errors."""
    project = indexed_tool_repo["project"]

    tool_call_1 = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {"symbol_name": "sym1", "project_id": str(project.id)},
                "id": "c1",
            }
        ],
    )
    tool_call_2 = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {"symbol_name": "sym2", "project_id": str(project.id)},
                "id": "c2",
            }
        ],
    )
    tool_call_3_rejected = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {"symbol_name": "sym3", "project_id": str(project.id)},
                "id": "c3",
            }
        ],
    )
    final_resp = AIMessage(content="Concluded with available context.")

    # Guard allows max 2 total calls
    strict_guard = ToolUsageGuard(max_total_calls=2)
    mock_provider = MockChatModelProvider(
        responses=[tool_call_1, tool_call_2, tool_call_3_rejected, final_resp]
    )
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
        tool_guard=strict_guard,
    )

    initial_state = create_initial_state(
        user_query="Test rate guard",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    result_state = await graph.ainvoke(initial_state)

    tool_results = result_state.get("tool_results", [])
    assert len(tool_results) == 3
    assert tool_results[0]["success"] is True
    assert tool_results[1]["success"] is True
    # 3rd call exceeded max_total_calls=2
    assert tool_results[2]["success"] is False
    assert "limit reached" in tool_results[2]["error"]
    assert result_state.get("final_answer") == final_resp.content


@pytest.mark.asyncio
async def test_agent_reasoning_structured_observability_logging(
    db_session: AsyncSession, test_user: User, indexed_tool_repo, caplog
):
    """Scenario I: Verifies that structured observability events are logged during execution."""
    project = indexed_tool_repo["project"]

    step1_search = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "HybridSearchEngine",
                    "project_id": str(project.id),
                },
                "id": "call_log_sym",
            }
        ],
    )
    step2_ans = AIMessage(content="Found HybridSearchEngine.")

    mock_provider = MockChatModelProvider(responses=[step1_search, step2_ans])
    graph = build_agent_graph(
        model_provider=mock_provider,
        db_session=db_session,
        user_id=test_user.id,
    )

    initial_state = create_initial_state(
        user_query="Find HybridSearchEngine",
        project_id=str(project.id),
        user_id=str(test_user.id),
    )

    with caplog.at_level(logging.INFO):
        await graph.ainvoke(initial_state)

    log_text = caplog.text
    # Verify expected structured event names
    assert "[agent.execution.started]" in log_text
    assert "[agent.tool.requested]" in log_text
    assert "tool=search_symbol" in log_text
    assert "[agent.tool.completed]" in log_text
    assert "[agent.execution.completed]" in log_text
