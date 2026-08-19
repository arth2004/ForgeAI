import datetime
import uuid

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """Payload for invoking the Forge AI repository intelligence agent."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User question or inquiry about the codebase.",
    )
    project_id: uuid.UUID = Field(
        ...,
        description="Target project ID providing organizational authorization.",
    )
    repository_id: uuid.UUID | None = Field(
        default=None,
        description="Target repository ID. If omitted, defaults to the project's primary repository.",
    )
    branch_id: uuid.UUID | None = Field(
        default=None,
        description="Target branch ID. If omitted, defaults to the repository's default branch.",
    )
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Optional session ID to reuse existing context. Validated against user and repository.",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the agent execution via Server-Sent Events (SSE).",
    )


class AgentSourceReference(BaseModel):
    """Citation or evidence reference returned alongside the agent's answer."""

    file_path: str = Field(..., description="Repository-relative file path of the source.")
    symbol_name: str | None = Field(
        default=None, description="Extracted AST symbol name if applicable."
    )
    start_line: int | None = Field(
        default=None, description="Starting line number of the cited chunk."
    )
    end_line: int | None = Field(
        default=None, description="Ending line number of the cited chunk."
    )
    commit_sha: str | None = Field(
        default=None, description="Commit SHA associated with the indexed index version."
    )


class AgentChatMetadata(BaseModel):
    """Operational telemetry and execution metadata for the agent reasoning loop."""

    iterations: int = Field(..., description="Number of agent reasoning turns executed.")
    tool_calls: int = Field(..., description="Total repository tool invocations made.")
    duration_ms: float = Field(..., description="Total execution time in milliseconds.")
    retrieved_sources_count: int = Field(
        ..., description="Total evidence chunks gathered in retrieved context."
    )


class AgentChatResponse(BaseModel):
    """Structured non-streaming response from the Forge AI agent."""

    session_id: uuid.UUID = Field(..., description="Unique agent session ID.")
    project_id: uuid.UUID = Field(..., description="Associated project ID.")
    repository_id: uuid.UUID | None = Field(
        default=None, description="Bound repository ID."
    )
    branch_id: uuid.UUID | None = Field(
        default=None, description="Bound branch ID."
    )
    answer: str = Field(..., description="Final grounded answer produced by the agent.")
    sources: list[AgentSourceReference] = Field(
        default_factory=list,
        description="Deduplicated source citations gathered during execution.",
    )
    metadata: AgentChatMetadata = Field(
        ..., description="Execution telemetry and performance metadata."
    )


class AgentSessionResponse(BaseModel):
    """Details of an agent operational context session."""

    session_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
