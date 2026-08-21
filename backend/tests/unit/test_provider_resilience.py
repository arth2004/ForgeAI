import json
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.exceptions import ModelProviderException
from app.agent.models import (
    GeminiChatModelProvider,
    MockChatModelProvider,
    OpenAIChatModelProvider,
    extract_retry_delay,
    get_chat_model_provider,
    sanitize_secret_text,
)

# ==============================================================================
# 1. Secret Sanitization & Error Security
# ==============================================================================


def test_secret_sanitization_all_providers():
    """Verifies that all provider tokens and bearer credentials are redacted."""
    raw = (
        "Error with AIzaSyD3949234823423 and sk-proj-1234567890abcdef and "
        "gsk_abcdef1234567890123456 and nvapi-9876543210fedcba and "
        "csk-1122334455667788 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and "
        "key=secret_12345_param in url"
    )
    sanitized = sanitize_secret_text(raw)
    assert "AIza" not in sanitized
    assert "sk-" not in sanitized
    assert "gsk_" not in sanitized
    assert "nvapi-" not in sanitized
    assert "csk-" not in sanitized
    assert "eyJhbGci" not in sanitized
    assert "secret_12345_param" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_OPENAI_KEY]" in sanitized
    assert "[REDACTED_GROQ_KEY]" in sanitized
    assert "[REDACTED_NVIDIA_KEY]" in sanitized
    assert "[REDACTED_CEREBRAS_KEY]" in sanitized
    assert "[REDACTED_TOKEN]" in sanitized


# ==============================================================================
# 2. 429 Retry Engine & Delay Extraction Priority Hierarchy
# ==============================================================================


def test_extract_retry_delay_priority_retry_after_header():
    """Priority 1: Retry-After header overrides other signals."""
    resp = httpx.Response(
        status_code=429,
        headers={"retry-after": "2.5", "x-ratelimit-reset-requests": "10.0"},
        text="Rate limit exceeded. Try again in 5.0s",
    )
    delay = extract_retry_delay(resp, attempt=0)
    assert delay == 2.5


def test_extract_retry_delay_priority_reset_header():
    """Priority 2: x-ratelimit-reset-* headers when Retry-After is absent."""
    resp = httpx.Response(
        status_code=429,
        headers={"x-ratelimit-reset-requests": "3.2"},
        text="Rate limit exceeded. Try again in 5.0s",
    )
    delay = extract_retry_delay(resp, attempt=0)
    assert delay == 3.2


def test_extract_retry_delay_priority_json_metadata():
    """Priority 3: Provider retry delay metadata in JSON payload."""
    resp = httpx.Response(
        status_code=429,
        json={"error": {"message": "Rate limit", "retry_after": 1.8}},
        text=json.dumps({"error": {"message": "Rate limit", "retry_after": 1.8}}),
    )
    delay = extract_retry_delay(resp, attempt=0)
    assert delay == 1.8


def test_extract_retry_delay_priority_parsed_text():
    """Priority 4: Parsed error text when no headers/metadata exist."""
    resp = httpx.Response(
        status_code=429,
        text="Rate limit reached for model. Please try again in 2.445s. Need more tokens?",
    )
    delay = extract_retry_delay(resp, attempt=0)
    assert abs(delay - (2.445 + 0.2)) < 0.01


def test_extract_retry_delay_fallback_backoff():
    """Priority 5: Bounded exponential backoff with jitter when no info is given."""
    resp = httpx.Response(status_code=429, text="Rate limit exceeded")
    delay_0 = extract_retry_delay(resp, attempt=0, default_base=1.0)
    delay_1 = extract_retry_delay(resp, attempt=1, default_base=1.0)
    assert 1.0 <= delay_0 <= 2.0
    assert 2.0 <= delay_1 <= 3.0


# ==============================================================================
# 3. Deterministic HTTP Mock Tests for OpenAI / Groq: 429, 401, 404, 400, & Retry
# ==============================================================================


@pytest.mark.asyncio
async def test_openai_provider_retry_on_429_success():
    """Section 6.H: Tests that 429 on attempt 1 followed by 200 on attempt 2 succeeds smoothly."""
    provider = OpenAIChatModelProvider(
        api_key="gsk_test_key_1234567890",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
        timeout_seconds=5.0,
    )

    resp_429 = httpx.Response(
        status_code=429,
        headers={"retry-after": "0.01"},
        text="Rate limit exceeded. Try again in 0.01s",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Grounded reasoning result.",
                        "tool_calls": [],
                    }
                }
            ]
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", side_effect=[resp_429, resp_200]):
        msg = await provider.ainvoke([HumanMessage(content="Hello")])
        assert msg.content == "Grounded reasoning result."


@pytest.mark.asyncio
async def test_openai_provider_retry_exhaustion_on_429():
    """Tests that exceeding max retries (3 retries = 4 attempts) raises ModelProviderException."""
    provider = OpenAIChatModelProvider(
        api_key="gsk_test_key_1234567890",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
        timeout_seconds=5.0,
    )

    resp_429 = httpx.Response(
        status_code=429,
        headers={"retry-after": "0.01"},
        text="Persistent rate limit exceeded",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch.object(
        httpx.AsyncClient, "post", side_effect=[resp_429, resp_429, resp_429, resp_429]
    ):
        with pytest.raises(ModelProviderException) as exc_info:
            await provider.ainvoke([HumanMessage(content="Hello")])
        assert exc_info.value.status_code == 429
        assert "groq API returned status 429" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,err_body",
    [
        (400, '{"error": {"message": "Invalid tool declaration schema"}}'),
        (401, '{"error": {"message": "Invalid API Key provided"}}'),
        (403, '{"error": {"message": "Forbidden access to model"}}'),
        (404, '{"error": {"message": "Model not found or no access"}}'),
        (422, '{"error": {"message": "Unprocessable Entity"}}'),
    ],
)
async def test_openai_provider_no_retry_on_permanent_errors(status_code, err_body):
    """Section 6.E, 6.F, 6.G: Verifies 400, 401, 403, 404, 422 immediately fail without retrying."""
    provider = OpenAIChatModelProvider(
        api_key="gsk_test_key_1234567890",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
        timeout_seconds=5.0,
    )

    resp_err = httpx.Response(
        status_code=status_code,
        text=err_body,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    mock_post = AsyncMock(return_value=resp_err)
    with patch.object(httpx.AsyncClient, "post", mock_post):
        with pytest.raises(ModelProviderException) as exc_info:
            await provider.ainvoke([HumanMessage(content="Hello")])
        assert exc_info.value.status_code == status_code
        # Ensure it was called EXACTLY ONCE (no retries attempted)
        assert mock_post.call_count == 1


# ==============================================================================
# 4. Deterministic HTTP Mock Tests for Google Gemini: 429, 401, 404, 400, & Retry
# ==============================================================================


@pytest.mark.asyncio
async def test_gemini_provider_retry_on_429_success():
    """Section 6.A & 6.H: Gemini 429 on attempt 1 followed by 200 on attempt 2 succeeds smoothly."""
    provider = GeminiChatModelProvider(
        api_key="AIza_test_gemini_key",
        model_name="gemini-3.1-pro-preview",
        timeout_seconds=5.0,
    )

    resp_429 = httpx.Response(
        status_code=429,
        headers={"retry-after": "0.01"},
        text="Gemini quota exceeded. Try again in 0.01s",
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        ),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Gemini grounded answer."}],
                        "role": "model",
                    }
                }
            ]
        },
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        ),
    )

    with patch.object(httpx.AsyncClient, "post", side_effect=[resp_429, resp_200]):
        msg = await provider.ainvoke([HumanMessage(content="Hello Gemini")])
        assert msg.content == "Gemini grounded answer."


@pytest.mark.asyncio
async def test_gemini_provider_retry_exhaustion_on_429():
    """Section 6.D: Gemini retry exhaustion after 3 retries (4 attempts)."""
    provider = GeminiChatModelProvider(
        api_key="AIza_test_gemini_key",
        model_name="gemini-3.1-pro-preview",
        timeout_seconds=5.0,
    )

    resp_429 = httpx.Response(
        status_code=429,
        headers={"retry-after": "0.001"},
        text="Rate limit exceeded",
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        ),
    )

    with patch.object(
        httpx.AsyncClient, "post", side_effect=[resp_429, resp_429, resp_429, resp_429]
    ):
        with pytest.raises(ModelProviderException) as exc_info:
            await provider.ainvoke([HumanMessage(content="Hello Gemini")])
        assert exc_info.value.status_code == 429
        assert "Gemini API returned status 429" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,err_body",
    [
        (400, '{"error": {"message": "Invalid Gemini parameter"}}'),
        (401, '{"error": {"message": "API_KEY_INVALID"}}'),
        (404, '{"error": {"message": "models/gemini-unsupported is not found"}}'),
    ],
)
async def test_gemini_provider_no_retry_on_permanent_errors(status_code, err_body):
    """Section 6.E, 6.F, 6.G: Gemini permanent 400, 401, 404 errors fail immediately without retry."""
    provider = GeminiChatModelProvider(
        api_key="AIza_test_gemini_key",
        model_name="gemini-3.1-pro-preview",
        timeout_seconds=5.0,
    )

    resp_err = httpx.Response(
        status_code=status_code,
        text=err_body,
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        ),
    )

    mock_post = AsyncMock(return_value=resp_err)
    with patch.object(httpx.AsyncClient, "post", mock_post):
        with pytest.raises(ModelProviderException) as exc_info:
            await provider.ainvoke([HumanMessage(content="Hello Gemini")])
        assert exc_info.value.status_code == status_code
        assert mock_post.call_count == 1


# ==============================================================================
# 5. Provider Failure Modes & Secret Protection (Section 7)
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_failure_modes_network_error_sanitization():
    """Section 7: Verifies network errors for all providers raise sanitized ModelProviderException."""
    # 1. Groq
    groq_p = OpenAIChatModelProvider(
        api_key="gsk_secret_12345",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
    )
    with patch.object(
        httpx.AsyncClient, "post", side_effect=httpx.ConnectError("Connection refused to gsk_secret_12345")
    ):
        with pytest.raises(ModelProviderException) as exc:
            await groq_p.ainvoke([HumanMessage(content="test")])
        assert "gsk_secret_12345" not in str(exc.value)
        assert "[REDACTED_GROQ_KEY]" in str(exc.value)
        assert exc.value.provider == "groq"

    # 2. Gemini
    gemini_p = GeminiChatModelProvider(
        api_key="AIzaSySecretGeminiKey12345",
        model_name="gemini-3.1-pro-preview",
    )
    with patch.object(
        httpx.AsyncClient,
        "post",
        side_effect=httpx.ConnectError("Failed AIzaSySecretGeminiKey12345 connect"),
    ):
        with pytest.raises(ModelProviderException) as exc:
            await gemini_p.ainvoke([HumanMessage(content="test")])
        assert "AIzaSySecretGeminiKey12345" not in str(exc.value)
        assert "[REDACTED_API_KEY]" in str(exc.value)
        assert exc.value.provider == "google"

    # 3. OpenAI
    openai_p = OpenAIChatModelProvider(
        api_key="sk-secret-openai-key-12345",
        model_name="gpt-4o",
        base_url="https://api.openai.com/v1",
        provider_label="openai",
    )
    with patch.object(
        httpx.AsyncClient, "post", side_effect=httpx.ConnectError("Failed sk-secret-openai-key-12345 connect")
    ):
        with pytest.raises(ModelProviderException) as exc:
            await openai_p.ainvoke([HumanMessage(content="test")])
        assert "sk-secret-openai-key-12345" not in str(exc.value)
        assert "[REDACTED_OPENAI_KEY]" in str(exc.value)
        assert exc.value.provider == "openai"

    # 4. OpenAI-Compatible (Cerebras / NVIDIA)
    custom_p = OpenAIChatModelProvider(
        api_key="csk-secret-cerebras-key-12345",
        model_name="llama-3.3-70b",
        base_url="https://api.cerebras.ai/v1",
        provider_label="openai_compatible",
    )
    with patch.object(
        httpx.AsyncClient,
        "post",
        side_effect=httpx.ConnectError("Failed csk-secret-cerebras-key-12345 connect"),
    ):
        with pytest.raises(ModelProviderException) as exc:
            await custom_p.ainvoke([HumanMessage(content="test")])
        assert "csk-secret-cerebras-key-12345" not in str(exc.value)
        assert "[REDACTED_CEREBRAS_KEY]" in str(exc.value)
        assert exc.value.provider == "openai_compatible"


# ==============================================================================
# 6. Provider Factory Selection & Generic Base URL (Sections 8 & 9)
# ==============================================================================


def test_provider_factory_selection():
    """Section 8: Verifies get_chat_model_provider factory resolves all supported provider aliases."""
    p_groq = get_chat_model_provider("groq", api_key="gsk_123", model_name="openai/gpt-oss-120b")
    assert p_groq.provider_name == "groq"
    assert p_groq.model_name == "openai/gpt-oss-120b"
    assert p_groq._base_url == "https://api.groq.com/openai/v1"

    p_gemini = get_chat_model_provider(
        "google", api_key="AIza_123", model_name="gemini-3.1-pro-preview"
    )
    assert p_gemini.provider_name == "google"
    assert p_gemini.model_name == "gemini-3.1-pro-preview"

    p_gemini_alias = get_chat_model_provider("gemini", api_key="AIza_123")
    assert p_gemini_alias.provider_name == "google"

    p_openai = get_chat_model_provider("openai", api_key="sk_123", model_name="gpt-4o")
    assert p_openai.provider_name == "openai"
    assert p_openai._base_url == "https://api.openai.com/v1"

    p_custom = get_chat_model_provider(
        "openai_compatible",
        api_key="csk_cerebras_123",
        model_name="llama-3.3-70b",
    )
    assert p_custom.provider_name == "openai_compatible"
    assert p_custom.model_name == "llama-3.3-70b"

    p_mock = get_chat_model_provider("mock")
    assert p_mock.provider_name == "mock"

    with pytest.raises(ModelProviderException) as exc_info:
        get_chat_model_provider("unsupported_vendor_xyz")
    assert "Unsupported chat model provider" in str(exc_info.value)


def test_generic_openai_compatible_custom_base_url():
    """Section 9: Verifies generic OpenAI-compatible provider supports arbitrary URLs without branching."""
    urls = [
        ("https://api.cerebras.ai/v1", "llama-3.3-70b"),
        ("https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct"),
        ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
        ("https://models.inference.ai.azure.com", "gpt-4o-mini"),
    ]
    for url, model in urls:
        provider = OpenAIChatModelProvider(
            api_key="test_key",
            model_name=model,
            base_url=url,
            provider_label="openai_compatible",
        )
        assert provider._base_url == url.rstrip("/")
        assert provider.model_name == model
        assert provider.provider_name == "openai_compatible"


# ==============================================================================
# 7. Tool Calling & Multi-turn Execution Compatibility (Section 10)
# ==============================================================================


@pytest.mark.asyncio
async def test_openai_provider_tool_call_parsing():
    """Section 10: Verifies that tool_calls returned in OpenAI chat completions payload are properly parsed."""
    provider = OpenAIChatModelProvider(
        api_key="gsk_test_key",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
    )

    tc_id = str(uuid.uuid4())
    resp_payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": "search_repository",
                                "arguments": json.dumps({"query": "authentication", "top_k": 5}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    resp_200 = httpx.Response(
        status_code=200,
        json=resp_payload,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", return_value=resp_200):
        ai_msg = await provider.ainvoke([HumanMessage(content="Where is auth implemented?")])
        assert len(ai_msg.tool_calls) == 1
        tc = ai_msg.tool_calls[0]
        assert tc["name"] == "search_repository"
        assert tc["args"] == {"query": "authentication", "top_k": 5}
        assert tc["id"] == tc_id


@pytest.mark.asyncio
async def test_gemini_provider_tool_call_parsing():
    """Section 10: Verifies that tool_calls returned in Gemini generateContent payload are properly parsed."""
    provider = GeminiChatModelProvider(
        api_key="AIza_test_key",
        model_name="gemini-3.1-pro-preview",
    )

    resp_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "search_symbol",
                                "args": {"symbol_name": "verify_jwt_token", "limit": 10},
                            }
                        }
                    ],
                    "role": "model",
                }
            }
        ]
    }

    resp_200 = httpx.Response(
        status_code=200,
        json=resp_payload,
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        ),
    )

    with patch.object(httpx.AsyncClient, "post", return_value=resp_200):
        ai_msg = await provider.ainvoke([HumanMessage(content="Where is verify_jwt_token?")])
        assert len(ai_msg.tool_calls) == 1
        tc = ai_msg.tool_calls[0]
        assert tc["name"] == "search_symbol"
        assert tc["args"] == {"symbol_name": "verify_jwt_token", "limit": 10}
        assert tc["id"] is not None


def test_openai_provider_message_conversion():
    """Verifies proper mapping of SystemMessage, HumanMessage, AIMessage with tool_calls, and ToolMessage."""
    provider = OpenAIChatModelProvider(
        api_key="test_key",
        model_name="openai/gpt-oss-120b",
    )

    tc_id = "call_abc123"
    messages = [
        SystemMessage(content="You are Forge AI reasoning agent."),
        HumanMessage(content="Find JWT implementation"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_symbol",
                    "args": {"symbol_name": "create_access_token"},
                    "id": tc_id,
                }
            ],
        ),
        ToolMessage(content="Found in app/core/security.py line 45", tool_call_id=tc_id),
    ]

    payload = provider._convert_messages_to_openai_payload(messages)
    assert len(payload) == 4
    assert payload[0] == {"role": "system", "content": "You are Forge AI reasoning agent."}
    assert payload[1] == {"role": "user", "content": "Find JWT implementation"}
    assert payload[2]["role"] == "assistant"
    assert payload[2]["tool_calls"][0]["function"]["name"] == "search_symbol"
    assert payload[3] == {
        "role": "tool",
        "tool_call_id": tc_id,
        "content": "Found in app/core/security.py line 45",
    }


def test_gemini_provider_message_conversion():
    """Verifies proper mapping of Gemini payload with System, User, Model tool_calls, and FunctionResponse."""
    provider = GeminiChatModelProvider(
        api_key="AIza_test_key",
        model_name="gemini-3.1-pro-preview",
    )

    tc_id = "call_gemini_123"
    messages = [
        SystemMessage(content="You are Forge AI reasoning agent."),
        HumanMessage(content="Find JWT implementation"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_symbol",
                    "args": {"symbol_name": "create_access_token"},
                    "id": tc_id,
                }
            ],
        ),
        ToolMessage(
            content="Found in app/core/security.py line 45",
            name="search_symbol",
            tool_call_id=tc_id,
        ),
    ]

    payload = provider._convert_messages_to_gemini_payload(messages)
    assert "systemInstruction" in payload
    assert payload["systemInstruction"]["parts"][0]["text"] == "You are Forge AI reasoning agent."
    assert len(payload["contents"]) == 3
    assert payload["contents"][0]["role"] == "user"
    assert payload["contents"][1]["role"] == "model"
    assert "functionCall" in payload["contents"][1]["parts"][0]
    assert payload["contents"][2]["role"] == "function"
    assert payload["contents"][2]["parts"][0]["functionResponse"]["name"] == "search_symbol"


def test_tool_declarations_schemas_all_tools_present():
    """Section 10: Verifies search_repository, search_symbol, and get_file are present in both provider tool declarations."""
    gemini_p = GeminiChatModelProvider(api_key="AIza_key")
    gemini_decls = gemini_p._get_gemini_tools_declaration()[0]["functionDeclarations"]
    gemini_tool_names = {t["name"] for t in gemini_decls}
    assert gemini_tool_names == {"search_repository", "search_symbol", "get_file"}

    openai_p = OpenAIChatModelProvider(api_key="gsk_key")
    openai_decls = openai_p._get_openai_tools_declaration()
    openai_tool_names = {t["function"]["name"] for t in openai_decls}
    assert openai_tool_names == {"search_repository", "search_symbol", "get_file"}


# ==============================================================================
# 8. Multi-Tool Loop Sequence & Iteration Cap (Section 11)
# ==============================================================================


@pytest.mark.asyncio
async def test_multi_tool_sequence_reasoning_flow():
    """Section 11: Sequential tool calling across multiple turns preserves IDs and messages."""
    from app.agent.graph import build_agent_graph
    from app.agent.state import create_initial_state

    tc1_id = "call_search_repo_1"
    step1_msg = AIMessage(
        content="",
        tool_calls=[{"name": "search_repository", "args": {"query": "auth"}, "id": tc1_id}],
    )

    tc2_id = "call_search_symbol_2"
    step2_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_symbol", "args": {"symbol_name": "create_access_token"}, "id": tc2_id}
        ],
    )

    tc3_id = "call_get_file_3"
    step3_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_file", "args": {"file_path": "app/core/security.py"}, "id": tc3_id}
        ],
    )

    final_answer = AIMessage(
        content="JWT tokens are generated in `app/core/security.py` via `create_access_token`."
    )

    mock_provider = MockChatModelProvider(responses=[step1_msg, step2_msg, step3_msg, final_answer])

    dummy_user_id = uuid.uuid4()
    mock_db = AsyncMock()

    from app.agent.tools.base import ToolExecutionResult

    mock_tool = AsyncMock()
    mock_tool.name = "mock"
    mock_tool.aexecute = AsyncMock(
        return_value=ToolExecutionResult(
            tool_name="mock",
            success=True,
            data={"result": "mock tool data"},
        )
    )

    with patch("app.agent.graph.get_agent_tool_by_name", return_value=mock_tool):
        graph = build_agent_graph(
            model_provider=mock_provider,
            db_session=mock_db,
            user_id=dummy_user_id,
        )

        initial_state = create_initial_state(user_query="Where is auth implemented?")
        result_state = await graph.ainvoke(initial_state)

        assert result_state["final_answer"] == final_answer.content
        assert result_state["iteration_count"] == 4
        # Verify all tool results were collected
        assert len(result_state["tool_results"]) == 3
        # Verify tool messages mapped to calls in conversation history
        messages = result_state["messages"]
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 3
        assert tool_messages[0].tool_call_id == tc1_id
        assert tool_messages[1].tool_call_id == tc2_id
        assert tool_messages[2].tool_call_id == tc3_id


@pytest.mark.asyncio
async def test_multi_tool_loop_halts_at_max_iterations():
    """Section 11: Verifies loop terminates cleanly at MAX_AGENT_ITERATIONS = 5 if model loops tools indefinitely."""
    from app.agent.graph import MAX_AGENT_ITERATIONS, build_agent_graph
    from app.agent.state import create_initial_state
    from app.agent.tools.base import ToolExecutionResult

    # An infinite loop of tool calls
    infinite_tool_msg = AIMessage(
        content="",
        tool_calls=[{"name": "search_repository", "args": {"query": "auth"}, "id": "call_loop"}],
    )

    mock_provider = MockChatModelProvider(
        responses=[infinite_tool_msg] * 10  # more than 5
    )

    mock_tool = AsyncMock()
    mock_tool.name = "search_repository"
    mock_tool.aexecute = AsyncMock(
        return_value=ToolExecutionResult(
            tool_name="search_repository",
            success=True,
            data={"results": []},
        )
    )

    with patch("app.agent.graph.get_agent_tool_by_name", return_value=mock_tool):
        graph = build_agent_graph(
            model_provider=mock_provider,
            db_session=AsyncMock(),
            user_id=uuid.uuid4(),
            max_iterations=MAX_AGENT_ITERATIONS,
        )

        initial_state = create_initial_state(user_query="Search indefinitely")
        result_state = await graph.ainvoke(initial_state)

        # Iteration count must be exactly MAX_AGENT_ITERATIONS (5), halting router before executing 5th tool
        assert result_state["iteration_count"] == 5
        assert len(result_state["tool_results"]) == 4
