import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.config import AgentConfig
from app.agent.exceptions import (
    AgentConfigException,
    AgentException,
    AgentExecutionException,
    ModelProviderException,
)
from app.agent.models import (
    GeminiChatModelProvider,
    MockChatModelProvider,
    OpenAIChatModelProvider,
    get_chat_model_provider,
    sanitize_secret_text,
)
from app.agent.state import create_initial_state


def test_agent_state_creation_and_defaults():
    """Verifies that create_initial_state initializes AgentState with expected defaults and types."""
    state = create_initial_state(
        user_query="How do I configure Redis caching?",
        repository_id="repo-uuid-123",
        branch_id="branch-uuid-456",
        metadata={"session_id": "sess-789"},
    )

    assert state["user_query"] == "How do I configure Redis caching?"
    assert state["repository_id"] == "repo-uuid-123"
    assert state["branch_id"] == "branch-uuid-456"
    assert state["retrieved_context"] == []
    assert state["tool_results"] == []
    assert state["final_answer"] is None
    assert state["metadata"] == {"session_id": "sess-789"}

    # Verify initial messages
    assert len(state["messages"]) == 1
    assert isinstance(state["messages"][0], HumanMessage)
    assert state["messages"][0].content == "How do I configure Redis caching?"


def test_agent_state_with_custom_messages():
    """Verifies that create_initial_state preserves custom provided message histories."""
    history = [
        SystemMessage(content="You are a helpful coding assistant."),
        HumanMessage(content="Hello!"),
        AIMessage(content="Hi there! How can I help?"),
    ]
    state = create_initial_state(user_query="Next step", initial_messages=history)

    assert len(state["messages"]) == 3
    assert state["messages"][0].content == "You are a helpful coding assistant."
    assert state["messages"][1].content == "Hello!"
    assert state["messages"][2].content == "Hi there! How can I help?"


def test_agent_config_from_settings_and_overrides():
    """Verifies AgentConfig initialization from settings and runtime overrides."""
    config_default = AgentConfig.from_settings()
    assert config_default.provider in {"google", "openai", "mock"}
    assert config_default.temperature == 0.2
    assert config_default.max_tokens == 4096

    # Test explicit overrides
    config_custom = AgentConfig.from_settings(
        provider_override="openai",
        model_override="gpt-4o-mini",
        temperature_override=0.7,
        max_tokens_override=2048,
        timeout_override=30.0,
    )
    assert config_custom.provider == "openai"
    assert config_custom.model_name == "gpt-4o-mini"
    assert config_custom.temperature == 0.7
    assert config_custom.max_tokens == 2048
    assert config_custom.timeout_seconds == 30.0

    d = config_custom.to_dict()
    assert d["provider"] == "openai"
    assert d["model_name"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_mock_chat_model_provider():
    """Verifies that MockChatModelProvider returns deterministic responses and records call history."""
    mock_model = MockChatModelProvider(default_response="Mocked architecture analysis.")

    messages = [
        SystemMessage(content="System prompt"),
        HumanMessage(content="Explain the architecture."),
    ]
    response = await mock_model.ainvoke(messages)

    assert isinstance(response, AIMessage)
    assert response.content == "Mocked architecture analysis."
    assert len(mock_model.call_history) == 1
    assert mock_model.call_history[0] == messages

    # Test response override
    override_resp = await mock_model.ainvoke(messages, response_override="Custom override response.")
    assert override_resp.content == "Custom override response."


@pytest.mark.asyncio
async def test_mock_chat_model_provider_failure():
    """Verifies that MockChatModelProvider raises ModelProviderException when should_fail=True."""
    failing_model = MockChatModelProvider(
        should_fail=True, failure_message="Rate limit simulated."
    )

    with pytest.raises(ModelProviderException) as exc_info:
        await failing_model.ainvoke([HumanMessage(content="test")])

    assert exc_info.value.provider == "mock"
    assert "Rate limit simulated." in exc_info.value.message


def test_get_chat_model_provider_factory():
    """Verifies that get_chat_model_provider factory instantiates the correct provider implementations."""
    mock_p = get_chat_model_provider(provider="mock")
    assert isinstance(mock_p, MockChatModelProvider)
    assert mock_p.provider_name == "mock"

    openai_p = get_chat_model_provider(provider="openai", model_name="gpt-4o")
    assert isinstance(openai_p, OpenAIChatModelProvider)
    assert openai_p.provider_name == "openai"

    gemini_p = get_chat_model_provider(provider="google", model_name="gemini-1.5-flash")
    assert isinstance(gemini_p, GeminiChatModelProvider)
    assert gemini_p.provider_name == "google"

    with pytest.raises(ModelProviderException):
        get_chat_model_provider(provider="unsupported-vendor")


def test_sanitize_secret_text_redaction():
    """Verifies that sanitize_secret_text redacts Google API keys and OpenAI tokens."""
    raw_text = "Failed call with key AIzaSyD9876543210abcdefghijklmnopq and key=AIzaSyD9876543210abcdefghijklmnopq"
    sanitized = sanitize_secret_text(raw_text)
    assert "AIzaSyD" not in sanitized
    assert "[REDACTED" in sanitized

    openai_text = "Error with bearer sk-abcdef1234567890abcdef1234567890"
    assert "sk-abcdef" not in sanitize_secret_text(openai_text)


def test_agent_exceptions_hierarchy():
    """Verifies exception inheritance structure and details dictionary."""
    base_exc = AgentException("Base agent failure", details={"step": 1})
    assert base_exc.status_code == 500
    assert base_exc.details["step"] == 1

    prov_exc = ModelProviderException("Provider timeout", provider="google")
    assert prov_exc.status_code == 502
    assert prov_exc.details["provider"] == "google"

    exec_exc = AgentExecutionException("Node execution failure", node_name="agent")
    assert exec_exc.status_code == 500
    assert exec_exc.details["node_name"] == "agent"

    cfg_exc = AgentConfigException("Invalid temperature parameter")
    assert cfg_exc.status_code == 400
