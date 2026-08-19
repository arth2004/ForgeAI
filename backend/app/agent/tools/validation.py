import re
import uuid
from typing import Any

from app.agent.exceptions import AgentException


class ToolValidationError(AgentException):
    """Raised when tool input validation fails."""

    def __init__(self, message: str, field_name: str | None = None, details: dict[str, Any] | None = None):
        det = details or {}
        if field_name:
            det["field_name"] = field_name
        super().__init__(message=message, status_code=400, details=det)


class ToolAuthorizationError(AgentException):
    """Raised when tenant/project authorization for a tool invocation fails."""

    def __init__(self, message: str = "Access forbidden for project or repository."):
        super().__init__(message=message, status_code=403)


class RepositoryNotIndexedError(AgentException):
    """Raised when a repository or branch lacks an ACTIVE index version."""

    def __init__(self, message: str = "The selected repository does not have an ACTIVE index version."):
        super().__init__(message=message, status_code=404)


class ToolRateLimitError(AgentException):
    """Raised when execution-scoped tool usage limits are exceeded."""

    def __init__(self, message: str = "Tool invocation limit exceeded for this execution."):
        super().__init__(message=message, status_code=429)


def validate_query_text(query: str, min_length: int = 1, max_length: int = 1000) -> str:
    """Validates search query text."""
    if not isinstance(query, str):
        raise ToolValidationError("Query must be a string.", field_name="query")
    cleaned = query.strip()
    if len(cleaned) < min_length:
        raise ToolValidationError(
            f"Query cannot be empty or shorter than {min_length} characters.",
            field_name="query",
        )
    if len(cleaned) > max_length:
        raise ToolValidationError(
            f"Query exceeds maximum length of {max_length} characters.",
            field_name="query",
        )
    return cleaned


def validate_symbol_name(symbol_name: str, min_length: int = 1, max_length: int = 255) -> str:
    """Validates symbol query name."""
    if not isinstance(symbol_name, str):
        raise ToolValidationError("Symbol name must be a string.", field_name="symbol_name")
    cleaned = symbol_name.strip()
    if len(cleaned) < min_length:
        raise ToolValidationError("Symbol name cannot be empty.", field_name="symbol_name")
    if len(cleaned) > max_length:
        raise ToolValidationError(
            f"Symbol name exceeds maximum length of {max_length} characters.",
            field_name="symbol_name",
        )
    return cleaned


def validate_safe_file_path(file_path: str) -> str:
    """Validates repository file path and strictly rejects path traversal attempts.

    Rejects:
    - Relative parent traversals (../ or ..\\)
    - Null bytes
    - Windows drive prefixes (C:, D:)
    - UNC network paths
    """
    if not isinstance(file_path, str):
        raise ToolValidationError("File path must be a string.", field_name="file_path")

    cleaned = file_path.strip()
    if not cleaned:
        raise ToolValidationError("File path cannot be empty.", field_name="file_path")

    if "\x00" in cleaned:
        raise ToolValidationError("File path contains illegal null bytes.", field_name="file_path")

    # Reject path traversal patterns
    if ".." in cleaned or "../" in cleaned or "..\\" in cleaned:
        raise ToolValidationError(
            "Path traversal detected. Relative parent directory access ('..') is prohibited.",
            field_name="file_path",
        )

    # Reject Windows drive letters (e.g. C:\ or C:/)
    if re.match(r"^[a-zA-Z]:", cleaned):
        raise ToolValidationError(
            "Absolute local filesystem drive paths are prohibited.",
            field_name="file_path",
        )

    # Normalize forward slashes and strip leading slashes
    normalized = cleaned.replace("\\", "/").lstrip("/")
    if not normalized:
        raise ToolValidationError("File path cannot resolve to an empty path.", field_name="file_path")

    return normalized


def validate_top_k(top_k: int | None, default: int = 5, min_k: int = 1, max_k: int = 20) -> int:
    """Validates top_k retrieval limits."""
    if top_k is None:
        return default
    if not isinstance(top_k, int) or top_k < min_k or top_k > max_k:
        raise ToolValidationError(
            f"top_k must be an integer between {min_k} and {max_k}.",
            field_name="top_k",
        )
    return top_k


def validate_uuid(val: str | uuid.UUID | None, field_name: str, required: bool = True) -> uuid.UUID | None:
    """Validates and parses UUID parameters."""
    if val is None:
        if required:
            raise ToolValidationError(f"Field '{field_name}' is required.", field_name=field_name)
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, AttributeError):
        raise ToolValidationError(
            f"Field '{field_name}' must be a valid UUID string.",
            field_name=field_name,
        ) from None
