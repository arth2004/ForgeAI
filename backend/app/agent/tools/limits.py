from dataclasses import dataclass, field

from app.agent.tools.validation import ToolRateLimitError

# Maximum output thresholds to prevent context window flooding
MAX_SEARCH_RESULTS: int = 20
DEFAULT_SEARCH_RESULTS: int = 5

MAX_SYMBOL_RESULTS: int = 20
DEFAULT_SYMBOL_RESULTS: int = 10

MAX_FILE_CHARS: int = 16000  # ~4000 tokens per single file read
MAX_TOOL_OUTPUT_CHARS: int = 24000  # Global single-call text limit

MAX_TOOL_CALLS_PER_EXECUTION: int = 10
MAX_PER_TOOL_CALLS: dict[str, int] = {
    "search_repository": 6,
    "search_symbol": 6,
    "get_file": 6,
}


@dataclass
class ToolUsageGuard:
    """Execution-scoped guard tracking and enforcing bounded tool invocation limits."""

    max_total_calls: int = MAX_TOOL_CALLS_PER_EXECUTION
    max_per_tool_calls: dict[str, int] = field(default_factory=lambda: dict(MAX_PER_TOOL_CALLS))
    total_calls: int = 0
    calls_by_tool: dict[str, int] = field(default_factory=dict)

    def record_call(self, tool_name: str) -> None:
        """Checks limits and registers a tool invocation."""
        if self.total_calls >= self.max_total_calls:
            raise ToolRateLimitError(
                f"Execution tool call limit reached (max {self.max_total_calls} calls)."
            )

        tool_limit = self.max_per_tool_calls.get(tool_name, self.max_total_calls)
        current_tool_calls = self.calls_by_tool.get(tool_name, 0)
        if current_tool_calls >= tool_limit:
            raise ToolRateLimitError(
                f"Limit exceeded for tool '{tool_name}' (max {tool_limit} calls per execution)."
            )

        self.total_calls += 1
        self.calls_by_tool[tool_name] = current_tool_calls + 1


def truncate_tool_output(content: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncates oversized tool outputs while appending an explicit indicator."""
    if len(content) <= max_chars:
        return content
    truncated = content[:max_chars]
    remaining = len(content) - max_chars
    return f"{truncated}\n\n... [TRUNCATED: {remaining} additional characters omitted to preserve model context]"
