from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.agent.tools.file_viewer import FileViewerInput, FileViewerTool
from app.agent.tools.git_tools import (
    CommitChangesTool,
    CreateBranchInput,
    CreateBranchTool,
    CreatePullRequestTool,
    GitStatusInput,
    GitStatusTool,
    PushBranchTool,
)
from app.agent.tools.limits import (
    DEFAULT_SEARCH_RESULTS,
    DEFAULT_SYMBOL_RESULTS,
    MAX_FILE_CHARS,
    MAX_SEARCH_RESULTS,
    MAX_SYMBOL_RESULTS,
    MAX_TOOL_CALLS_PER_EXECUTION,
    ToolUsageGuard,
    truncate_tool_output,
)
from app.agent.tools.patch_tools import (
    ApplyPatchTool,
    ProposePatchInput,
    ProposePatchTool,
    RunTestsInput,
    RunTestsTool,
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


def get_agent_tools() -> list[BaseRepositoryTool]:
    """Returns the central registry of all Phase 4 & Phase 5 repository agent tools."""
    return [
        RepositorySearchTool(),
        SymbolSearchTool(),
        FileViewerTool(),
        ProposePatchTool(),
        RunTestsTool(),
        ApplyPatchTool(),
        CreateBranchTool(),
        GitStatusTool(),
        CommitChangesTool(),
        PushBranchTool(),
        CreatePullRequestTool(),
    ]


def get_agent_tool_by_name(tool_name: str) -> BaseRepositoryTool | None:
    """Finds a registered tool by its name."""
    for t in get_agent_tools():
        if t.name == tool_name:
            return t
    return None


__all__ = [
    "DEFAULT_SEARCH_RESULTS",
    "DEFAULT_SYMBOL_RESULTS",
    "FileViewerInput",
    "FileViewerTool",
    "MAX_FILE_CHARS",
    "MAX_SEARCH_RESULTS",
    "MAX_SYMBOL_RESULTS",
    "MAX_TOOL_CALLS_PER_EXECUTION",
    "ApplyPatchTool",
    "ProposePatchInput",
    "ProposePatchTool",
    "RunTestsInput",
    "RunTestsTool",
    "CreateBranchInput",
    "CreateBranchTool",
    "GitStatusInput",
    "GitStatusTool",
    "CommitChangesTool",
    "PushBranchTool",
    "CreatePullRequestTool",
    "RepositoryNotIndexedError",
    "RepositorySearchInput",
    "RepositorySearchTool",
    "SymbolSearchInput",
    "SymbolSearchTool",
    "ToolAuthorizationError",
    "ToolExecutionResult",
    "ToolRateLimitError",
    "ToolUsageGuard",
    "ToolValidationError",
    "get_agent_tool_by_name",
    "get_agent_tools",
    "truncate_tool_output",
    "validate_query_text",
    "validate_safe_file_path",
    "validate_symbol_name",
    "validate_top_k",
    "validate_uuid",
]


