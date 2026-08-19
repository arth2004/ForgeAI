import logging
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agent.exceptions import ModelProviderException
from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_secret_text(text: str) -> str:
    """Redacts API keys and sensitive tokens from error messages."""
    text = re.sub(r"AIza[0-9A-Za-z\-_]{10,}", "[REDACTED_API_KEY]", text)
    text = re.sub(r"sk-[0-9A-Za-z\-_]{10,}", "[REDACTED_OPENAI_KEY]", text)
    text = re.sub(r"(key=)[^& \n\)]+", r"\1[REDACTED]", text)
    return text


class BaseChatModelProvider(ABC):
    """Abstract interface decoupling agent reasoning from specific LLM vendors."""

    def __init__(self, model_name: str, temperature: float = 0.2, max_tokens: int | None = 4096):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name identifier of the provider (e.g. 'google', 'openai', 'mock')."""
        ...

    @abstractmethod
    async def ainvoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> BaseMessage:
        """Asynchronously sends messages to the model provider and returns a standard BaseMessage."""
        ...


class MockChatModelProvider(BaseChatModelProvider):
    """Deterministic mock provider for zero-API-key testing and offline verification."""

    def __init__(
        self,
        default_response: str | AIMessage = "Mock agent reasoning completed.",
        model_name: str = "mock-model",
        temperature: float = 0.0,
        max_tokens: int | None = 1000,
        should_fail: bool = False,
        failure_message: str = "Simulated model provider failure.",
        responses: list[AIMessage | str] | None = None,
    ):
        super().__init__(model_name=model_name, temperature=temperature, max_tokens=max_tokens)
        self.default_response = default_response
        self.should_fail = should_fail
        self.failure_message = failure_message
        self.call_history: list[list[BaseMessage]] = []
        self._responses: list[AIMessage | str] = list(responses) if responses is not None else []
        self._response_idx: int = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    async def ainvoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> BaseMessage:
        self.call_history.append(list(messages))
        if self.should_fail:
            raise ModelProviderException(
                message=self.failure_message,
                provider=self.provider_name,
            )

        if self._responses and self._response_idx < len(self._responses):
            resp = self._responses[self._response_idx]
            self._response_idx += 1
            if isinstance(resp, str):
                return AIMessage(content=resp, id=str(uuid.uuid4()))
            if isinstance(resp, AIMessage):
                return AIMessage(
                    content=resp.content,
                    tool_calls=list(resp.tool_calls) if resp.tool_calls else [],
                    id=str(uuid.uuid4()),
                )
            return resp

        custom_response = kwargs.get("response_override")
        if custom_response is not None:
            if isinstance(custom_response, str):
                return AIMessage(content=custom_response, id=str(uuid.uuid4()))
            return custom_response
        if isinstance(self.default_response, AIMessage):
            return AIMessage(
                content=self.default_response.content,
                tool_calls=list(self.default_response.tool_calls) if self.default_response.tool_calls else [],
                id=str(uuid.uuid4()),
            )
        return AIMessage(content=self.default_response, id=str(uuid.uuid4()))


class GeminiChatModelProvider(BaseChatModelProvider):
    """Google Gemini LLM provider using direct HTTPS API."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = 4096,
        timeout_seconds: float = 60.0,
    ):
        resolved_model = model_name or settings.AGENT_GEMINI_MODEL or "gemini-3.1-pro-preview"
        super().__init__(model_name=resolved_model, temperature=temperature, max_tokens=max_tokens)
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "google"

    def _get_gemini_tools_declaration(self) -> list[dict[str, Any]]:
        """Returns Google Gemini function declarations for Phase 4 repository tools."""
        return [
            {
                "functionDeclarations": [
                    {
                        "name": "search_repository",
                        "description": (
                            "Searches repository code and documentation using dense and sparse hybrid retrieval. "
                            "Use for conceptual inquiries, feature discovery, and locating implementations."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {
                                    "type": "STRING",
                                    "description": "The search query to match against code and docs.",
                                },
                                "top_k": {
                                    "type": "INTEGER",
                                    "description": "Maximum number of evidence chunks to retrieve (default: 5).",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "search_symbol",
                        "description": (
                            "Searches AST symbol declarations (classes, functions, methods, interfaces) in the repository."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "symbol_name": {
                                    "type": "STRING",
                                    "description": "The symbol identifier to search for (e.g. 'verify_jwt_token').",
                                },
                                "limit": {
                                    "type": "INTEGER",
                                    "description": "Maximum symbol results to return (default: 10).",
                                },
                            },
                            "required": ["symbol_name"],
                        },
                    },
                    {
                        "name": "get_file",
                        "description": (
                            "Retrieves the content of a specific repository source file with optional line slicing."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "file_path": {
                                    "type": "STRING",
                                    "description": "Repository relative file path (e.g. 'app/core/security.py').",
                                },
                                "start_line": {
                                    "type": "INTEGER",
                                    "description": "Optional starting line number (1-indexed).",
                                },
                                "end_line": {
                                    "type": "INTEGER",
                                    "description": "Optional ending line number (1-indexed).",
                                },
                            },
                            "required": ["file_path"],
                        },
                    },
                ]
            }
        ]

    def _convert_messages_to_gemini_payload(self, messages: Sequence[BaseMessage]) -> dict[str, Any]:
        contents = []
        system_instruction = None

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_instruction = {"parts": [{"text": str(msg.content)}]}
            elif isinstance(msg, HumanMessage):
                contents.append({"role": "user", "parts": [{"text": str(msg.content)}]})
            elif isinstance(msg, AIMessage):
                parts: list[dict[str, Any]] = []
                if msg.content:
                    parts.append({"text": str(msg.content)})
                tool_calls = getattr(msg, "tool_calls", None) or []
                for tc in tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.get("name"),
                            "args": tc.get("args", {}),
                        }
                    })
                if not parts:
                    parts.append({"text": ""})
                contents.append({"role": "model", "parts": parts})
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", None) or getattr(msg, "tool_call_id", None) or "tool_result"
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"output": str(msg.content)},
                        }
                    }],
                })
            else:
                contents.append({"role": "user", "parts": [{"text": str(msg.content)}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
            },
            "tools": self._get_gemini_tools_declaration(),
        }
        if self.max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = self.max_tokens
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        return payload

    async def ainvoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> BaseMessage:
        if not self._api_key:
            raise ModelProviderException(
                message="GEMINI_API_KEY is not configured in settings or environment.",
                provider=self.provider_name,
            )

        payload = self._convert_messages_to_gemini_payload(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)

            if response.status_code != 200:
                sanitized_error = sanitize_secret_text(response.text)
                err_detail = sanitized_error
                try:
                    err_json = response.json()
                    if isinstance(err_json, dict) and "error" in err_json:
                        err_obj = err_json["error"]
                        if isinstance(err_obj, dict) and "message" in err_obj:
                            err_detail = err_obj["message"]
                except Exception:
                    pass

                if response.status_code == 404:
                    raise ModelProviderException(
                        message=f"Gemini model '{self.model_name}' is unavailable or unsupported: {err_detail}",
                        provider=self.provider_name,
                        status_code=404,
                    )
                raise ModelProviderException(
                    message=f"Gemini API returned status {response.status_code}: {err_detail}",
                    provider=self.provider_name,
                    status_code=response.status_code,
                )

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return AIMessage(content="")

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            for part in parts:
                if "text" in part and part["text"]:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append({
                        "name": fc.get("name"),
                        "args": fc.get("args", {}),
                        "id": str(uuid.uuid4()),
                    })

            text_content = "".join(text_parts)
            return AIMessage(content=text_content, tool_calls=tool_calls)

        except ModelProviderException:
            raise
        except Exception as e:
            sanitized = sanitize_secret_text(str(e))
            logger.error(f"Gemini chat invocation error: {sanitized}")
            raise ModelProviderException(
                message=f"Gemini connection failed: {sanitized}",
                provider=self.provider_name,
            ) from None


class OpenAIChatModelProvider(BaseChatModelProvider):
    """OpenAI chat completions provider using direct HTTPS API."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int | None = 4096,
        timeout_seconds: float = 60.0,
    ):
        super().__init__(model_name=model_name, temperature=temperature, max_tokens=max_tokens)
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "openai"

    def _convert_messages_to_openai_payload(self, messages: Sequence[BaseMessage]) -> list[dict[str, str]]:
        formatted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                formatted.append({"role": "assistant", "content": str(msg.content)})
            else:
                formatted.append({"role": "user", "content": str(msg.content)})
        return formatted

    async def ainvoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> BaseMessage:
        if not self._api_key:
            raise ModelProviderException(
                message="OPENAI_API_KEY is not configured in settings or environment.",
                provider=self.provider_name,
            )

        formatted_messages = self._convert_messages_to_openai_payload(messages)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": self.temperature,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                sanitized_error = sanitize_secret_text(response.text)
                err_detail = sanitized_error
                try:
                    err_json = response.json()
                    if isinstance(err_json, dict) and "error" in err_json:
                        err_obj = err_json["error"]
                        if isinstance(err_obj, dict) and "message" in err_obj:
                            err_detail = err_obj["message"]
                except Exception:
                    pass
                raise ModelProviderException(
                    message=f"OpenAI API returned status {response.status_code}: {err_detail}",
                    provider=self.provider_name,
                    status_code=response.status_code,
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return AIMessage(content="")

            content = choices[0].get("message", {}).get("content", "")
            return AIMessage(content=content)

        except ModelProviderException:
            raise
        except Exception as e:
            sanitized = sanitize_secret_text(str(e))
            logger.error(f"OpenAI chat invocation error: {sanitized}")
            raise ModelProviderException(
                message=f"OpenAI connection failed: {sanitized}",
                provider=self.provider_name,
            ) from None


def get_chat_model_provider(
    provider: str | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModelProvider:
    """Factory resolving chat model provider instance based on settings or explicit parameters."""
    prov = (provider or settings.AGENT_DEFAULT_PROVIDER).lower().strip()
    temp = temperature if temperature is not None else settings.AGENT_TEMPERATURE
    tokens = max_tokens if max_tokens is not None else settings.AGENT_MAX_TOKENS

    if prov == "mock":
        return MockChatModelProvider(
            model_name=model_name or "mock-model",
            temperature=temp,
            max_tokens=tokens,
        )
    elif prov == "openai":
        return OpenAIChatModelProvider(
            api_key=api_key,
            model_name=model_name or settings.AGENT_OPENAI_MODEL,
            temperature=temp,
            max_tokens=tokens,
        )
    elif prov in {"google", "gemini"}:
        return GeminiChatModelProvider(
            api_key=api_key,
            model_name=model_name or settings.AGENT_GEMINI_MODEL,
            temperature=temp,
            max_tokens=tokens,
        )
    else:
        raise ModelProviderException(
            message=f"Unsupported chat model provider: '{prov}'. Supported: 'google', 'openai', 'mock'.",
            provider=prov,
        )
