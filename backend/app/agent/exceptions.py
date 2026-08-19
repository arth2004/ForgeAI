from typing import Any

from fastapi import status

from app.core.exceptions import ForgeAIException


class AgentException(ForgeAIException):
    """Base exception for all agent runtime subsystem errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)


class ModelProviderException(AgentException):
    """Raised when an LLM provider invocation fails (e.g. rate limit, authentication, network)."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        details: dict[str, Any] | None = None,
    ):
        self.provider = provider
        det = details or {}
        det["provider"] = provider
        super().__init__(message=message, status_code=status_code, details=det)


class AgentExecutionException(AgentException):
    """Raised when an error occurs during LangGraph state transitions or node execution."""

    def __init__(
        self,
        message: str,
        node_name: str | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        det = details or {}
        if node_name:
            det["node_name"] = node_name
        super().__init__(message=message, status_code=status_code, details=det)


class AgentConfigException(AgentException):
    """Raised when invalid or incomplete agent configuration is detected."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)
