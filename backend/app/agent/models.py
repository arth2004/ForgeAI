import asyncio
import json
import logging
import random
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import httpx
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
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
    text = re.sub(r"\bAIza[0-9A-Za-z\-_]{10,}", "[REDACTED_API_KEY]", text)
    text = re.sub(r"\bgsk_[0-9A-Za-z\-_]{10,}", "[REDACTED_GROQ_KEY]", text)
    text = re.sub(r"\bnvapi-[0-9A-Za-z\-_]{10,}", "[REDACTED_NVIDIA_KEY]", text)
    text = re.sub(r"\bcsk-[0-9A-Za-z\-_]{10,}", "[REDACTED_CEREBRAS_KEY]", text)
    text = re.sub(r"\bsk-[0-9A-Za-z\-_]{10,}", "[REDACTED_OPENAI_KEY]", text)
    text = re.sub(r"(Bearer\s+)[0-9A-Za-z\-_\.]{10,}", r"\1[REDACTED_TOKEN]", text)
    text = re.sub(r"(key=)[^& \n\)]+", r"\1[REDACTED]", text)
    return text


def extract_retry_delay(
    response: httpx.Response,
    attempt: int,
    default_base: float = 1.5,
) -> float:
    """Calculates retry delay adhering to priority hierarchy:
    1. Retry-After header (seconds)
    2. x-ratelimit-reset-* headers
    3. Provider retry-delay metadata (JSON payload)
    4. Parsed error text
    5. Bounded exponential backoff with jitter
    """
    # 1. Retry-After header
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            val = float(retry_after.strip())
            return min(max(val, 0.1), 10.0)
        except ValueError:
            pass

    # 2. x-ratelimit-reset-* headers
    for hdr in [
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset",
        "retry-after-ms",
    ]:
        reset_val = response.headers.get(hdr)
        if reset_val:
            try:
                val = float(reset_val.strip())
                if hdr == "retry-after-ms":
                    val = val / 1000.0
                elif val > 1_000_000_000_000:  # epoch ms
                    val = (val / 1000.0) - time.time()
                elif val > 1_000_000_000:  # epoch seconds
                    val = val - time.time()
                if val > 0:
                    return min(val, 10.0)
            except ValueError:
                pass

    # 3. Provider retry-delay metadata in JSON
    try:
        data = response.json()
        if isinstance(data, dict):
            err_obj = data.get("error", {})
            if isinstance(err_obj, dict):
                for key in ["retry_after", "retry_delay", "retryAfter", "retryDelay"]:
                    if key in err_obj:
                        val = float(err_obj[key])
                        return min(max(val, 0.1), 10.0)
                details = err_obj.get("details", [])
                if isinstance(details, list):
                    for item in details:
                        if isinstance(item, dict) and "retryDelay" in item:
                            delay_str = str(item["retryDelay"]).rstrip("s")
                            return min(max(float(delay_str), 0.1), 10.0)
    except Exception:
        pass

    # 4. Parsed error text
    try:
        err_text = response.text
        match = re.search(
            r"(?:try again in|retry in|wait)\s+([0-9\.]+)\s*(?:s|seconds)?",
            err_text,
            re.IGNORECASE,
        )
        if match:
            try:
                return min(float(match.group(1)) + 0.2, 15.0)
            except ValueError:
                pass
    except Exception:
        pass

    # 5. Bounded exponential backoff with jitter
    jitter = random.uniform(0.0, 0.25)
    backoff = (default_base * (2**attempt)) + jitter
    return min(backoff, 15.0)


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

    @abstractmethod
    def astream(
        self, messages: Sequence[BaseMessage], **kwargs: Any
    ) -> AsyncGenerator[AIMessageChunk, None]:
        """Asynchronously streams incremental model output chunks."""
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

        if self.default_response != "Mock agent reasoning completed.":
            if isinstance(self.default_response, AIMessage):
                return AIMessage(
                    content=self.default_response.content,
                    tool_calls=list(self.default_response.tool_calls) if self.default_response.tool_calls else [],
                    id=str(uuid.uuid4()),
                )
            return AIMessage(content=self.default_response, id=str(uuid.uuid4()))


        # Check if the prompt is asking for an ImplementationPlan or feature planning
        user_text = ""
        is_planning = False
        for msg in messages:
            content_lower = str(msg.content).lower()
            if "implementationplan" in content_lower or "phase: planning" in content_lower:
                is_planning = True
            if isinstance(msg, HumanMessage):
                user_text = str(msg.content)

        # Check if this is the first turn without tool messages (simulate repository search)
        has_tool_messages = any(isinstance(m, ToolMessage) for m in messages)


        if not has_tool_messages and ("plan" in user_text.lower() or "add" in user_text.lower() or "fix" in user_text.lower() or is_planning):
            # Simulate initial tool search
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "name": "search_repository",
                        "args": {"query": user_text or "rate limiting patch validation"},
                    }
                ],
                id=str(uuid.uuid4()),
            )

        if is_planning or any(k in user_text.lower() for k in ["plan", "add", "fix", "feature", "patch", "endpoint"]):
            summary_title = user_text[:60] if user_text else "Add rate limiting validation to patch proposal endpoint"
            plan_payload = {
                "summary": f"Plan: {summary_title}",
                "problem_statement": user_text or "Enforce safety validations on repository patch proposal endpoints.",
                "approach": "Investigate affected routers, add rate limiter dependency guards, and verify with pytest suite.",
                "affected_files": [
                    {
                        "file_path": "app/api/v1/agent.py",
                        "change_type": "MODIFY",
                        "reason": "Enforce request verification and session binding.",
                        "symbols": ["propose_patch", "apply_patch"]
                    }
                ],
                "new_files": [],
                "deleted_files": [],
                "test_strategy": "pytest tests/integration/test_phase5c_patch_and_test_api.py -v",
                "risks": ["Potential 429 response if rate limit window is exceeded during rapid tests."],
                "sources": []
            }
            return AIMessage(content=json.dumps(plan_payload, indent=2), id=str(uuid.uuid4()))

        return AIMessage(
            content=f"Forge AI repository investigation complete for query: '{user_text}'. All codebase references verified.",
            id=str(uuid.uuid4()),
        )

    async def astream(
        self, messages: Sequence[BaseMessage], **kwargs: Any
    ) -> AsyncGenerator[AIMessageChunk, None]:
        """Asynchronously streams chunks for mock responses."""
        if self.should_fail:
            self.call_history.append(list(messages))
            raise ModelProviderException(
                message=self.failure_message,
                provider=self.provider_name,
            )

        full_msg = await self.ainvoke(messages, **kwargs)

        tool_calls = getattr(full_msg, "tool_calls", None) or []
        if tool_calls:
            yield AIMessageChunk(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": tc.get("id", str(uuid.uuid4())),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }
                        for tc in tool_calls
                    ]
                },
                tool_calls=tool_calls,
                id=full_msg.id,
            )
            return

        content_str = str(full_msg.content)
        if not content_str:
            yield AIMessageChunk(content="", id=full_msg.id)
            return

        words = re.findall(r"\S+|\s+", content_str)
        if not words:
            yield AIMessageChunk(content=content_str, id=full_msg.id)
            return

        for word in words:
            yield AIMessageChunk(content=word, id=full_msg.id)




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
        resolved_model = model_name or settings.AGENT_GEMINI_MODEL or "gemini-3.1-flash-lite"
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

    def _convert_messages_to_gemini_payload(
        self, messages: Sequence[BaseMessage], **kwargs: Any
    ) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
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
                    parts.append(
                        {
                            "functionCall": {
                                "name": tc.get("name"),
                                "args": tc.get("args", {}),
                            }
                        }
                    )
                if not parts:
                    parts.append({"text": ""})
                contents.append({"role": "model", "parts": parts})
            elif isinstance(msg, ToolMessage):
                tool_name = (
                    getattr(msg, "name", None)
                    or getattr(msg, "tool_call_id", None)
                    or "tool_result"
                )
                contents.append(
                    {
                        "role": "function",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": tool_name,
                                    "response": {"output": str(msg.content)},
                                }
                            }
                        ],
                    }
                )
            else:
                contents.append({"role": "user", "parts": [{"text": str(msg.content)}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
            },
        }
        tools_decl = kwargs.get("tools")
        if tools_decl is None and "tools" not in kwargs:
            tools_decl = self._get_gemini_tools_declaration()
        if tools_decl:
            payload["tools"] = tools_decl

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

        payload = self._convert_messages_to_gemini_payload(messages, **kwargs)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        max_retries = 3
        start_time = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429 and attempt < max_retries:
                    wait_seconds = extract_retry_delay(response, attempt)
                    logger.warning(
                        f"[agent.model.rate_limited] provider={self.provider_name} "
                        f"model={self.model_name} attempt={attempt + 1}/{max_retries} "
                        f"retry_delay_seconds={wait_seconds:.2f}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

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
                        tool_calls.append(
                            {
                                "name": fc.get("name"),
                                "args": fc.get("args", {}),
                                "id": str(uuid.uuid4()),
                            }
                        )

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(
                    f"[agent.model.invoked] provider={self.provider_name} "
                    f"model={self.model_name} duration_ms={duration_ms} "
                    f"retries_used={attempt} tool_calls_count={len(tool_calls)}"
                )

                text_content = "".join(text_parts)
                return AIMessage(content=text_content, tool_calls=tool_calls)

            except ModelProviderException:
                raise
            except Exception as e:
                sanitized = sanitize_secret_text(str(e))
                logger.error(
                    f"[agent.model.error] provider={self.provider_name} model={self.model_name} error={sanitized}"
                )
                raise ModelProviderException(
                    message=f"Gemini connection failed: {sanitized}",
                    provider=self.provider_name,
                ) from None

        raise ModelProviderException(
            message=f"Gemini API rate limit exceeded after {max_retries} retries.",
            provider=self.provider_name,
            status_code=429,
        )

    async def astream(
        self, messages: Sequence[BaseMessage], **kwargs: Any
    ) -> AsyncGenerator[AIMessageChunk, None]:
        if not self._api_key:
            raise ModelProviderException(
                message="GEMINI_API_KEY is not configured in settings or environment.",
                provider=self.provider_name,
            )

        payload = self._convert_messages_to_gemini_payload(messages, **kwargs)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:streamGenerateContent?alt=sse"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        max_retries = 3
        start_time = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code == 429 and attempt < max_retries:
                            await response.aread()
                            wait_seconds = extract_retry_delay(response, attempt)
                            logger.warning(
                                f"[agent.model.rate_limited] provider={self.provider_name} "
                                f"model={self.model_name} attempt={attempt + 1}/{max_retries} "
                                f"retry_delay_seconds={wait_seconds:.2f}"
                            )
                            await asyncio.sleep(wait_seconds)
                            continue

                        if response.status_code != 200:
                            err_body = await response.aread()
                            sanitized_error = sanitize_secret_text(err_body.decode("utf-8", errors="replace"))
                            err_detail = sanitized_error
                            try:
                                err_json = json.loads(err_body)
                                if isinstance(err_json, dict) and "error" in err_json:
                                    err_obj = err_json["error"]
                                    if isinstance(err_obj, dict) and "message" in err_obj:
                                        err_detail = err_obj["message"]
                            except Exception:
                                pass
                            raise ModelProviderException(
                                message=f"Gemini API returned status {response.status_code}: {err_detail}",
                                provider=self.provider_name,
                                status_code=response.status_code,
                            )

                        chunk_count = 0
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                try:
                                    chunk_data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue

                                candidates = chunk_data.get("candidates", [])
                                if not candidates:
                                    continue
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    if "text" in part and part["text"]:
                                        chunk_count += 1
                                        yield AIMessageChunk(content=part["text"])
                                    if "functionCall" in part:
                                        fc = part["functionCall"]
                                        chunk_count += 1
                                        yield AIMessageChunk(
                                            content="",
                                            additional_kwargs={"functionCall": fc},
                                        )

                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        logger.info(
                            f"[agent.model.stream_completed] provider={self.provider_name} "
                            f"model={self.model_name} duration_ms={duration_ms} chunks={chunk_count}"
                        )
                        return

            except ModelProviderException:
                raise
            except Exception as e:
                sanitized = sanitize_secret_text(str(e))
                logger.error(
                    f"[agent.model.error] provider={self.provider_name} model={self.model_name} error={sanitized}"
                )
                raise ModelProviderException(
                    message=f"Gemini connection failed: {sanitized}",
                    provider=self.provider_name,
                ) from None



class OpenAIChatModelProvider(BaseChatModelProvider):
    """OpenAI-compatible chat completions provider.

    Supports OpenAI, Groq, NVIDIA NIM, Cerebras, OpenRouter, and any provider
    exposing the standard ``/v1/chat/completions`` endpoint.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int | None = 4096,
        timeout_seconds: float = 60.0,
        base_url: str = "https://api.openai.com/v1",
        provider_label: str = "openai",
    ):
        super().__init__(model_name=model_name, temperature=temperature, max_tokens=max_tokens)
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._timeout = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._provider_label = provider_label

    @property
    def provider_name(self) -> str:
        return self._provider_label

    def _get_openai_tools_declaration(self) -> list[dict[str, Any]]:
        """Returns OpenAI-format function declarations for Phase 4 repository tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_repository",
                    "description": (
                        "Searches repository code and documentation using dense and sparse hybrid retrieval. "
                        "Use for conceptual inquiries, feature discovery, and locating implementations."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to match against code and docs.",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Maximum number of evidence chunks to retrieve (default: 5).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_symbol",
                    "description": (
                        "Searches AST symbol declarations (classes, functions, methods, interfaces) in the repository."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol_name": {
                                "type": "string",
                                "description": "The symbol identifier to search for (e.g. 'verify_jwt_token').",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum symbol results to return (default: 10).",
                            },
                        },
                        "required": ["symbol_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_file",
                    "description": (
                        "Retrieves the content of a specific repository source file with optional line slicing."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Repository relative file path (e.g. 'app/core/security.py').",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Optional starting line number (1-indexed).",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Optional ending line number (1-indexed).",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
            },
        ]

    def _convert_messages_to_openai_payload(
        self, messages: Sequence[BaseMessage]
    ) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                entry: dict[str, Any] = {"role": "assistant"}
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    entry["content"] = str(msg.content) if msg.content else None
                    tool_calls_payload = []
                    for tc in tool_calls:
                        tc_args = tc.get("args", {})
                        if isinstance(tc_args, str):
                            arg_str = tc_args
                        else:
                            try:
                                arg_str = json.dumps(tc_args)
                            except Exception:
                                arg_str = "{}"
                        tool_calls_payload.append(
                            {
                                "id": tc.get("id", str(uuid.uuid4())),
                                "type": "function",
                                "function": {
                                    "name": str(tc.get("name", "")).split(".")[-1].split(":")[-1],
                                    "arguments": arg_str,
                                },
                            }
                        )
                    entry["tool_calls"] = tool_calls_payload
                else:
                    entry["content"] = str(msg.content)
                formatted.append(entry)
            elif isinstance(msg, ToolMessage):
                tool_call_id = getattr(msg, "tool_call_id", None) or str(uuid.uuid4())
                formatted.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": str(msg.content),
                    }
                )
            elif isinstance(msg, HumanMessage):
                formatted.append({"role": "user", "content": str(msg.content)})
            else:
                formatted.append({"role": "user", "content": str(msg.content)})
        return formatted

    async def ainvoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> BaseMessage:
        if not self._api_key:
            raise ModelProviderException(
                message=f"API key for {self.provider_name} provider is not configured in settings or environment.",
                provider=self.provider_name,
            )

        formatted_messages = self._convert_messages_to_openai_payload(messages)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": self.temperature,
        }
        tools_decl = kwargs.get("tools")
        if tools_decl is None and "tools" not in kwargs:
            tools_decl = self._get_openai_tools_declaration()
        if tools_decl:
            payload["tools"] = tools_decl
        if "tool_choice" in kwargs:
            payload["tool_choice"] = kwargs["tool_choice"]

        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_retries = kwargs.get("max_retries", 3)
        start_time = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429 and attempt < max_retries:
                    wait_seconds = extract_retry_delay(response, attempt)
                    logger.warning(
                        f"[agent.model.rate_limited] provider={self.provider_name} "
                        f"model={self.model_name} attempt={attempt + 1}/{max_retries} "
                        f"retry_delay_seconds={wait_seconds:.2f}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

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
                        message=f"{self.provider_name} API returned status {response.status_code}: {err_detail}",
                        provider=self.provider_name,
                        status_code=response.status_code,
                    )

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    return AIMessage(content="")

                message_data = choices[0].get("message", {})
                content = message_data.get("content", "") or ""
                raw_tool_calls = message_data.get("tool_calls") or []

                tool_calls: list[dict[str, Any]] = []
                for tc in raw_tool_calls:
                    func = tc.get("function", {})
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    tool_calls.append(
                        {
                            "name": func.get("name"),
                            "args": args,
                            "id": tc.get("id", str(uuid.uuid4())),
                        }
                    )

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(
                    f"[agent.model.invoked] provider={self.provider_name} "
                    f"model={self.model_name} duration_ms={duration_ms} "
                    f"retries_used={attempt} tool_calls_count={len(tool_calls)}"
                )

                return AIMessage(content=content, tool_calls=tool_calls)

            except ModelProviderException:
                raise
            except Exception as e:
                sanitized = sanitize_secret_text(str(e))
                logger.error(
                    f"[agent.model.error] provider={self.provider_name} "
                    f"model={self.model_name} error={sanitized}"
                )
                raise ModelProviderException(
                    message=f"{self.provider_name} connection failed: {sanitized}",
                    provider=self.provider_name,
                ) from None

        raise ModelProviderException(
            message=f"{self.provider_name} API rate limit exceeded after {max_retries} retries.",
            provider=self.provider_name,
            status_code=429,
        )

    async def astream(
        self, messages: Sequence[BaseMessage], **kwargs: Any
    ) -> AsyncGenerator[AIMessageChunk, None]:
        if not self._api_key:
            raise ModelProviderException(
                message=f"API key for {self.provider_name} provider is not configured in settings or environment.",
                provider=self.provider_name,
            )

        formatted_messages = self._convert_messages_to_openai_payload(messages)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "stream": True,
        }
        tools_decl = kwargs.get("tools")
        if tools_decl is None and "tools" not in kwargs:
            tools_decl = self._get_openai_tools_declaration()
        if tools_decl:
            payload["tools"] = tools_decl
        if "tool_choice" in kwargs:
            payload["tool_choice"] = kwargs["tool_choice"]

        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_retries = kwargs.get("max_retries", 3)
        start_time = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code == 429 and attempt < max_retries:
                            await response.aread()
                            wait_seconds = extract_retry_delay(response, attempt)
                            logger.warning(
                                f"[agent.model.rate_limited] provider={self.provider_name} "
                                f"model={self.model_name} attempt={attempt + 1}/{max_retries} "
                                f"retry_delay_seconds={wait_seconds:.2f}"
                            )
                            await asyncio.sleep(wait_seconds)
                            continue

                        if response.status_code != 200:
                            err_body = await response.aread()
                            sanitized_error = sanitize_secret_text(err_body.decode("utf-8", errors="replace"))
                            err_detail = sanitized_error
                            try:
                                err_json = json.loads(err_body)
                                if isinstance(err_json, dict) and "error" in err_json:
                                    err_obj = err_json["error"]
                                    if isinstance(err_obj, dict) and "message" in err_obj:
                                        err_detail = err_obj["message"]
                            except Exception:
                                pass
                            raise ModelProviderException(
                                message=f"{self.provider_name} API returned status {response.status_code}: {err_detail}",
                                provider=self.provider_name,
                                status_code=response.status_code,
                            )

                        chunk_count = 0
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue

                                choices = chunk_data.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})
                                content_piece = delta.get("content")
                                raw_tool_calls = delta.get("tool_calls")

                                if content_piece:
                                    chunk_count += 1
                                    yield AIMessageChunk(content=content_piece)
                                elif raw_tool_calls:
                                    chunk_count += 1
                                    yield AIMessageChunk(
                                        content="",
                                        additional_kwargs={"tool_calls": raw_tool_calls},
                                    )

                        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        logger.info(
                            f"[agent.model.stream_completed] provider={self.provider_name} "
                            f"model={self.model_name} duration_ms={duration_ms} chunks={chunk_count}"
                        )
                        return

            except ModelProviderException:
                raise
            except Exception as e:
                sanitized = sanitize_secret_text(str(e))
                logger.error(
                    f"[agent.model.error] provider={self.provider_name} model={self.model_name} error={sanitized}"
                )
                raise ModelProviderException(
                    message=f"{self.provider_name} connection failed: {sanitized}",
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
            base_url="https://api.openai.com/v1",
            provider_label="openai",
        )
    elif prov == "groq":
        return OpenAIChatModelProvider(
            api_key=api_key or settings.GROQ_API_KEY,
            model_name=model_name or settings.GROQ_MODEL,
            temperature=temp,
            max_tokens=tokens,
            base_url=settings.GROQ_BASE_URL,
            provider_label="groq",
        )
    elif prov == "openai_compatible":
        return OpenAIChatModelProvider(
            api_key=api_key or settings.OPENAI_COMPATIBLE_API_KEY,
            model_name=model_name or settings.OPENAI_COMPATIBLE_MODEL,
            temperature=temp,
            max_tokens=tokens,
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL,
            provider_label="openai_compatible",
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
            message=f"Unsupported chat model provider: '{prov}'. Supported: 'google', 'openai', 'groq', 'openai_compatible', 'mock'.",
            provider=prov,
        )
