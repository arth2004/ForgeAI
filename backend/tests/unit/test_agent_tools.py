import uuid

import pytest

from app.agent.tools.file_viewer import FileViewerInput, FileViewerTool
from app.agent.tools.limits import (
    ToolUsageGuard,
    truncate_tool_output,
)
from app.agent.tools.repository_search import (
    RepositorySearchInput,
    RepositorySearchTool,
)
from app.agent.tools.symbol_search import SymbolSearchInput, SymbolSearchTool
from app.agent.tools.validation import (
    RepositoryNotIndexedError,
    ToolAuthorizationError,
    ToolRateLimitError,
    ToolValidationError,
    validate_query_text,
    validate_safe_file_path,
    validate_symbol_name,
    validate_top_k,
    validate_uuid,
)


def test_validate_query_text():
    """Verifies query text validation boundaries."""
    assert validate_query_text("Where is authentication?") == "Where is authentication?"

    with pytest.raises(ToolValidationError) as exc_info:
        validate_query_text("")
    assert exc_info.value.details.get("field_name") == "query"

    with pytest.raises(ToolValidationError):
        validate_query_text("   ")

    with pytest.raises(ToolValidationError):
        validate_query_text("a" * 1001)


def test_validate_symbol_name():
    """Verifies symbol name validation."""
    assert validate_symbol_name("HybridSearchEngine") == "HybridSearchEngine"

    with pytest.raises(ToolValidationError):
        validate_symbol_name("")

    with pytest.raises(ToolValidationError):
        validate_symbol_name("a" * 256)


def test_validate_safe_file_path_security():
    """Strict security test verifying path traversal and arbitrary filesystem access rejection."""
    assert validate_safe_file_path("backend/app/core/config.py") == "backend/app/core/config.py"
    assert validate_safe_file_path("/backend/app/core/config.py") == "backend/app/core/config.py"
    assert validate_safe_file_path(r"backend\app\core\config.py") == "backend/app/core/config.py"

    # Rejection of path traversal ../
    with pytest.raises(ToolValidationError) as exc_info:
        validate_safe_file_path("../../etc/passwd")
    assert "Path traversal detected" in exc_info.value.message

    with pytest.raises(ToolValidationError):
        validate_safe_file_path("backend/../../secret.env")

    with pytest.raises(ToolValidationError):
        validate_safe_file_path(r"backend\..\..\secret.env")

    # Rejection of null bytes
    with pytest.raises(ToolValidationError):
        validate_safe_file_path("backend/app.py\x00.png")

    # Rejection of Windows drive letters
    with pytest.raises(ToolValidationError):
        validate_safe_file_path("C:\\Windows\\System32\\cmd.exe")

    with pytest.raises(ToolValidationError):
        validate_safe_file_path("D:/projects/secret.py")

    # Rejection of empty paths
    with pytest.raises(ToolValidationError):
        validate_safe_file_path("")

    with pytest.raises(ToolValidationError):
        validate_safe_file_path("///")


def test_validate_top_k():
    """Verifies top_k validation limits."""
    assert validate_top_k(None, default=5) == 5
    assert validate_top_k(10) == 10
    assert validate_top_k(1) == 1
    assert validate_top_k(20) == 20

    with pytest.raises(ToolValidationError):
        validate_top_k(0)

    with pytest.raises(ToolValidationError):
        validate_top_k(21)


def test_validate_uuid():
    """Verifies UUID validation and conversion."""
    uid = uuid.uuid4()
    assert validate_uuid(uid, "id") == uid
    assert validate_uuid(str(uid), "id") == uid
    assert validate_uuid(None, "id", required=False) is None

    with pytest.raises(ToolValidationError):
        validate_uuid("invalid-uuid-string", "id")

    with pytest.raises(ToolValidationError):
        validate_uuid(None, "id", required=True)


def test_tool_usage_guard_limits():
    """Verifies that ToolUsageGuard enforces bounded tool calls per execution."""
    guard = ToolUsageGuard(max_total_calls=3)

    guard.record_call("search_repository")
    guard.record_call("search_repository")
    guard.record_call("get_file")
    assert guard.total_calls == 3

    # Exceeding total calls raises ToolRateLimitError
    with pytest.raises(ToolRateLimitError) as exc_info:
        guard.record_call("search_symbol")
    assert "Execution tool call limit reached" in exc_info.value.message


def test_truncate_tool_output():
    """Verifies tool output text truncation and preservation."""
    short_text = "Small code snippet."
    assert truncate_tool_output(short_text, max_chars=100) == short_text

    long_text = "A" * 500
    truncated = truncate_tool_output(long_text, max_chars=200)
    assert len(truncated) > 200
    assert "TRUNCATED" in truncated
    assert truncated.startswith("A" * 200)


def test_tool_schemas_and_metadata():
    """Verifies tool metadata and Pydantic argument schemas."""
    search_tool = RepositorySearchTool()
    assert search_tool.name == "search_repository"
    assert search_tool.args_schema == RepositorySearchInput

    symbol_tool = SymbolSearchTool()
    assert symbol_tool.name == "search_symbol"
    assert symbol_tool.args_schema == SymbolSearchInput

    file_tool = FileViewerTool()
    assert file_tool.name == "get_file"
    assert file_tool.args_schema == FileViewerInput


def test_tool_exception_types():
    """Verifies tool domain exception status codes."""
    auth_err = ToolAuthorizationError()
    assert auth_err.status_code == 403

    unindexed_err = RepositoryNotIndexedError()
    assert unindexed_err.status_code == 404

    rate_err = ToolRateLimitError()
    assert rate_err.status_code == 429
