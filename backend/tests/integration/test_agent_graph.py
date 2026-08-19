import inspect

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.exceptions import AgentExecutionException
from app.agent.graph import build_agent_graph
from app.agent.models import MockChatModelProvider
from app.agent.state import create_initial_state


def test_build_and_compile_agent_graph():
    """Verifies that build_agent_graph constructs a valid, runnable LangGraph CompiledStateGraph."""
    mock_provider = MockChatModelProvider(default_response="Compilation verified.")
    graph = build_agent_graph(model_provider=mock_provider)

    assert graph is not None
    # Verify graph node topology
    assert "agent" in graph.nodes


@pytest.mark.asyncio
async def test_agent_graph_execution_with_mock_model():
    """Verifies full execution lifecycle: START -> agent_node -> END with mock model provider."""
    mock_provider = MockChatModelProvider(
        default_response="Tree-sitter parser is implemented in chunker.py"
    )
    graph = build_agent_graph(model_provider=mock_provider)

    initial_state = create_initial_state(
        user_query="Where is the parser implemented?",
        repository_id="repo-001",
        branch_id="branch-001",
        metadata={"user_id": "user-999"},
    )

    result_state = await graph.ainvoke(initial_state)

    # 1. Verify messages sequence
    messages = result_state.get("messages", [])
    assert len(messages) == 2
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "Where is the parser implemented?"
    assert isinstance(messages[1], AIMessage)
    assert messages[1].content == "Tree-sitter parser is implemented in chunker.py"

    # 2. Verify final_answer
    assert (
        result_state.get("final_answer")
        == "Tree-sitter parser is implemented in chunker.py"
    )

    # 3. Verify contextual fields are preserved
    assert result_state.get("repository_id") == "repo-001"
    assert result_state.get("branch_id") == "branch-001"
    assert result_state.get("metadata") == {"user_id": "user-999"}
    assert result_state.get("retrieved_context") == []
    assert result_state.get("tool_results") == []

    # 4. Verify mock provider call history received SystemMessage and HumanMessage
    assert len(mock_provider.call_history) == 1
    assert isinstance(mock_provider.call_history[0][0], SystemMessage)
    assert mock_provider.call_history[0][1].content == "Where is the parser implemented?"


@pytest.mark.asyncio
async def test_agent_graph_handles_provider_failure():
    """Verifies that model provider errors inside the graph raise sanitized AgentExecutionException."""
    failing_provider = MockChatModelProvider(
        should_fail=True,
        failure_message="Simulated upstream quota error (key=AIzaSecret12345).",
    )
    graph = build_agent_graph(model_provider=failing_provider)

    initial_state = create_initial_state(user_query="Test failure handling")

    with pytest.raises(AgentExecutionException) as exc_info:
        await graph.ainvoke(initial_state)

    err = exc_info.value
    assert err.status_code == 500
    assert err.details.get("node_name") == "agent"
    # Ensure raw secret is not leaked in exception message
    assert "AIzaSecret" not in err.message


def test_phase_4_architectural_boundary_static_check():
    """Strict architectural boundary check:

    Asserts that Phase 4 core foundation modules (config, exceptions, models, state) have ZERO direct imports from:
    - app.models (ORM/database models)
    - app.services.retrieval (Phase 3 retrieval pipeline)
    - app.services.ingestion (Phase 3 ingestion pipeline)
    - app.services.parser (Tree-sitter parser)
    - app.workers (ARQ tasks)
    - sqlalchemy.orm (direct database sessions)
    """
    import app.agent.config
    import app.agent.exceptions
    import app.agent.models
    import app.agent.state

    foundation_modules = [
        app.agent.config,
        app.agent.exceptions,
        app.agent.models,
        app.agent.state,
    ]

    forbidden_patterns = [
        "app.models",
        "app.services.retrieval",
        "app.services.ingestion",
        "app.services.parser",
        "app.workers",
        "sqlalchemy.orm",
        "AsyncSessionLocal",
    ]

    for mod in foundation_modules:
        source_code = inspect.getsource(mod)
        for pattern in forbidden_patterns:
            assert pattern not in source_code, (
                f"Architectural boundary violation in {mod.__name__}: "
                f"found forbidden import/reference '{pattern}'. "
                f"Core agent foundation must NOT directly access databases, ORM models, or retrieval services."
            )
