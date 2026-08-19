import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.agent.tools.limits import truncate_tool_output
from app.agent.tools.validation import (
    validate_query_text,
    validate_top_k,
    validate_uuid,
)
from app.services.retrieval.hybrid import HybridSearchEngine

logger = logging.getLogger(__name__)


class RepositorySearchInput(BaseModel):
    """Input parameters for the repository hybrid search tool."""

    query: str = Field(
        ...,
        description="Natural language search query or code concept (e.g. 'Where is JWT authentication implemented?').",
    )
    project_id: str = Field(
        ...,
        description="UUID identifier of the project containing the target repository.",
    )
    repository_id: str | None = Field(
        default=None,
        description="Optional UUID identifier of a specific repository within the project.",
    )
    branch_id: str | None = Field(
        default=None,
        description="Optional UUID identifier of a specific repository branch.",
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of relevant code evidence chunks to retrieve (1 to 20).",
    )


class RepositorySearchTool(BaseRepositoryTool):
    """Tool exposing Phase 3 3-stage hybrid search (dense pgvector + sparse GIN BM25 + symbol match)."""

    @property
    def name(self) -> str:
        return "search_repository"

    @property
    def description(self) -> str:
        return (
            "Searches the indexed repository for code implementation, classes, functions, or architectural logic "
            "using hybrid semantic, keyword, and symbol retrieval. Returns top ranked evidence chunks with file paths, "
            "line numbers, symbols, context headers, and code content."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return RepositorySearchInput

    async def aexecute(self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any) -> ToolExecutionResult:
        query_raw = kwargs.get("query", "")
        project_id_raw = kwargs.get("project_id")
        repository_id_raw = kwargs.get("repository_id")
        branch_id_raw = kwargs.get("branch_id")
        top_k_raw = kwargs.get("top_k", 5)

        # 1. Validation
        query = validate_query_text(query_raw)
        top_k = validate_top_k(top_k_raw)
        project_uuid = validate_uuid(project_id_raw, "project_id", required=True)
        assert project_uuid is not None
        repo_uuid = validate_uuid(repository_id_raw, "repository_id", required=False)
        branch_uuid = validate_uuid(branch_id_raw, "branch_id", required=False)

        # 2. Authorization & Active Index Verification
        await self.verify_project_access(user_id=user_id, project_id=project_uuid, db=db)
        await self.get_active_index_version(
            project_id=project_uuid,
            repository_id=repo_uuid,
            branch_id=branch_uuid,
            db=db,
        )

        # 3. Invoke Phase 3 Hybrid Search Engine
        logger.info(
            f"[Tool:search_repository] Executing hybrid search | project={project_uuid} "
            f"top_k={top_k} query='{query[:60]}'"
        )
        evidence_chunks = await HybridSearchEngine.search(
            project_id=project_uuid,
            query=query,
            branch_id=branch_uuid,
            top_k=top_k,
            session_override=db,
        )

        # 4. Format structured output for LLM
        formatted_results = []
        for rank_idx, chunk in enumerate(evidence_chunks, start=1):
            chunk_data = {
                "rank": rank_idx,
                "file_path": chunk.file_path,
                "symbol_name": chunk.symbol_name,
                "chunk_type": chunk.chunk_type,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "context_header": chunk.context_header,
                "content": truncate_tool_output(chunk.content, max_chars=4000),
                "rrf_score": round(chunk.rrf_score, 4),
                "commit_sha": chunk.commit_sha,
                "branch_name": chunk.branch_name,
            }
            formatted_results.append(chunk_data)

        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={
                "query": query,
                "total_results": len(formatted_results),
                "results": formatted_results,
            },
        )
