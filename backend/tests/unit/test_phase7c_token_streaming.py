import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agent.exceptions import ModelProviderException
from app.agent.graph import agent_node
from app.agent.models import (
    BaseChatModelProvider,
    MockChatModelProvider,
    OpenAIChatModelProvider,
)
from app.agent.state import AgentState
from app.models.auth import User
from app.schemas.agent import AgentChatRequest
from app.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_mock_chat_model_provider_astream_text_chunks():
    """Verify MockChatModelProvider.astream yields multiple incremental text chunks."""
    provider = MockChatModelProvider(default_response="Authentication uses JWT tokens.")
    messages = [HumanMessage(content="Explain auth")]

    chunks: list[AIMessageChunk] = []
    async for chunk in provider.astream(messages):
        chunks.append(chunk)

    assert len(chunks) > 1
    full_text = "".join(str(c.content) for c in chunks)
    assert full_text == "Authentication uses JWT tokens."


@pytest.mark.asyncio
async def test_mock_chat_model_provider_astream_failure():
    """Verify MockChatModelProvider(should_fail=True) raises ModelProviderException."""
    provider = MockChatModelProvider(should_fail=True, failure_message="Stream connection refused")
    messages = [HumanMessage(content="Hello")]

    with pytest.raises(ModelProviderException) as exc_info:
        async for _ in provider.astream(messages):
            pass

    assert "Stream connection refused" in str(exc_info.value)
    assert exc_info.value.provider == "mock"


@pytest.mark.asyncio
async def test_openai_chat_model_provider_astream_text_chunks():
    """Verify OpenAIChatModelProvider.astream parses SSE chunks from OpenAI-compatible API."""
    provider = OpenAIChatModelProvider(
        api_key="mock-groq-key",
        model_name="openai/gpt-oss-120b",
    )

    sse_lines = [
        b'data: {"choices": [{"delta": {"content": "PostgreSQL "}}]}\n',
        b'data: {"choices": [{"delta": {"content": "pgvector "}}]}\n',
        b'data: {"choices": [{"delta": {"content": "storage."}}]}\n',
        b"data: [DONE]\n",
    ]

    class MockAsyncResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for line in sse_lines:
                yield line.decode("utf-8")

    with patch("httpx.AsyncClient.stream", return_value=MockAsyncResponse()):
        chunks: list[AIMessageChunk] = []
        async for chunk in provider.astream([HumanMessage(content="Explain storage")]):
            chunks.append(chunk)

    assert len(chunks) == 3
    assert [c.content for c in chunks] == ["PostgreSQL ", "pgvector ", "storage."]


@pytest.mark.asyncio
async def test_openai_chat_model_provider_astream_tool_chunks():
    """Verify OpenAIChatModelProvider.astream yields tool call deltas correctly."""
    provider = OpenAIChatModelProvider(
        api_key="mock-groq-key",
        model_name="openai/gpt-oss-120b",
    )

    sse_lines = [
        b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "search_repository", "arguments": "{\\"query\\": "}}]}}]}\n',
        b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\\"auth\\"}"}}]}}]}\n',
        b"data: [DONE]\n",
    ]

    class MockAsyncResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for line in sse_lines:
                yield line.decode("utf-8")

    with patch("httpx.AsyncClient.stream", return_value=MockAsyncResponse()):
        chunks: list[AIMessageChunk] = []
        async for chunk in provider.astream([HumanMessage(content="Find auth")]):
            chunks.append(chunk)

    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.content == ""
        assert "tool_calls" in chunk.additional_kwargs


@pytest.mark.asyncio
async def test_agent_node_streams_tokens_to_callback():
    """Verify agent_node delivers text chunks to on_token callback without waiting for complete answer."""
    provider = MockChatModelProvider(default_response="Tokens stream in real time.")
    state: AgentState = {
        "user_query": "Test streaming",
        "messages": [HumanMessage(content="Test streaming")],
        "iteration_count": 0,
        "retrieved_context": [],
    }

    received_tokens: list[str] = []

    def on_token_cb(token: str):
        received_tokens.append(token)

    result = await agent_node(
        state=state,
        model_provider_override=provider,
        on_token_override=on_token_cb,
    )

    assert len(received_tokens) > 1
    assert "".join(received_tokens) == "Tokens stream in real time."
    assert result["final_answer"] == "Tokens stream in real time."
    assert len(result["messages"]) == 1


@pytest.mark.asyncio
async def test_agent_node_accumulates_tool_calls_without_emitting_tokens():
    """Verify agent_node accumulates tool call chunk deltas and NEVER sends them to on_token."""
    class ToolStreamingMockProvider(BaseChatModelProvider):
        @property
        def provider_name(self) -> str:
            return "mock"

        async def ainvoke(self, messages, **kwargs):
            return AIMessage(
                content="",
                tool_calls=[{"name": "search_repository", "args": {"query": "auth"}, "id": "call_123"}],
            )

        async def astream(self, messages, **kwargs):
            yield AIMessageChunk(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_123",
                            "function": {"name": "search_repository", "arguments": '{"query": '},
                        }
                    ]
                },
            )
            yield AIMessageChunk(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": '"auth"}'},
                        }
                    ]
                },
            )

    provider = ToolStreamingMockProvider(model_name="mock-tool-streamer")
    state: AgentState = {
        "user_query": "Find auth code",
        "messages": [HumanMessage(content="Find auth code")],
        "iteration_count": 0,
        "retrieved_context": [],
    }

    received_tokens: list[str] = []

    def on_token_cb(token: str):
        received_tokens.append(token)

    result = await agent_node(
        state=state,
        model_provider_override=provider,
        on_token_override=on_token_cb,
    )

    # Tool calls must NEVER be emitted as text tokens
    assert len(received_tokens) == 0
    # But tool calls must be reconstructed in the resulting AIMessage
    last_msg = result["messages"][-1]
    assert len(last_msg.tool_calls) == 1
    assert last_msg.tool_calls[0]["name"] == "search_repository"
    assert last_msg.tool_calls[0]["args"] == {"query": "auth"}
    assert last_msg.tool_calls[0]["id"] == "call_123"


@pytest.mark.asyncio
async def test_agent_service_stream_chat_event_ordering():
    """Verify AgentService.stream_chat produces deterministic SSE event ordering with real tokens."""
    provider = MockChatModelProvider(default_response="Deterministic SSE stream verified.")

    db_mock = AsyncMock()
    service = AgentService(db=db_mock)

    user = User(
        id=uuid.uuid4(),
        email="test@forgeai.dev",
        full_name="stream_tester",
        is_active=True,
    )

    session_mock = MagicMock()
    session_mock.id = uuid.uuid4()
    session_mock.project_id = uuid.uuid4()
    session_mock.repository_id = uuid.uuid4()
    session_mock.branch_id = None

    service.resolve_and_authorize_context = AsyncMock(return_value=session_mock)

    request = AgentChatRequest(
        project_id=session_mock.project_id,
        repository_id=session_mock.repository_id,
        message="Explain streaming pipeline",
    )

    events: list[dict[str, Any]] = []
    async for sse_raw in service.stream_chat(user=user, request=request, model_provider_override=provider):
        lines = sse_raw.strip().split("\n")
        event_name = ""
        data_obj = {}
        for line in lines:
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_obj = json.loads(line[6:].strip())
        if event_name:
            events.append({"event": event_name, "data": data_obj})

    event_names = [e["event"] for e in events]
    assert event_names[0] == "session.created"
    assert event_names[1] == "agent.started"
    assert "agent.token" in event_names
    assert event_names[-1] == "agent.completed"

    # Verify tokens combine to the completed answer
    tokens = [e["data"]["content"] for e in events if e["event"] == "agent.token"]
    assert len(tokens) > 1
    assert "".join(tokens) == "Deterministic SSE stream verified."
    assert events[-1]["data"]["answer"] == "Deterministic SSE stream verified."


@pytest.mark.asyncio
async def test_agent_service_stream_chat_error_terminates_without_completed():
    """Verify that when a model fails during streaming, agent.error is emitted and agent.completed is NOT emitted."""
    provider = MockChatModelProvider(should_fail=True, failure_message="Groq HTTP 429 rate limit")

    db_mock = AsyncMock()
    service = AgentService(db=db_mock)

    user = User(
        id=uuid.uuid4(),
        email="test@forgeai.dev",
        full_name="stream_tester",
        is_active=True,
    )

    session_mock = MagicMock()
    session_mock.id = uuid.uuid4()
    session_mock.project_id = uuid.uuid4()
    session_mock.repository_id = uuid.uuid4()
    session_mock.branch_id = None

    service.resolve_and_authorize_context = AsyncMock(return_value=session_mock)

    request = AgentChatRequest(
        project_id=session_mock.project_id,
        repository_id=session_mock.repository_id,
        message="Should fail with error",
    )

    events: list[dict[str, Any]] = []
    async for sse_raw in service.stream_chat(user=user, request=request, model_provider_override=provider):
        lines = sse_raw.strip().split("\n")
        event_name = ""
        data_obj = {}
        for line in lines:
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_obj = json.loads(line[6:].strip())
        if event_name:
            events.append({"event": event_name, "data": data_obj})

    event_names = [e["event"] for e in events]
    assert "agent.error" in event_names
    assert "agent.completed" not in event_names
