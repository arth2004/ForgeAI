import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.agent.tools.limits import truncate_tool_output
from app.agent.tools.validation import (
    validate_safe_file_path,
    validate_symbol_name,
    validate_top_k,
    validate_uuid,
)
from app.models.codebase import CodeChunk, RepositoryFile, RepositoryIndexVersion

logger = logging.getLogger(__name__)


class SymbolSearchInput(BaseModel):
    """Input parameters for the repository symbol search tool."""

    symbol_name: str = Field(
        ...,
        description="Name of the function, class, method, or interface symbol to find (e.g. 'HybridSearchEngine').",
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
    file_path_filter: str | None = Field(
        default=None,
        description="Optional path substring filter to constrain symbol lookup to specific modules or files.",
    )
    limit: int = Field(
        default=10,
        description="Maximum number of symbol definitions to return (1 to 20).",
    )


class SymbolSearchTool(BaseRepositoryTool):
    """Tool finding indexed AST symbol definitions (classes, functions, methods, interfaces)."""

    @property
    def name(self) -> str:
        return "search_symbol"

    @property
    def description(self) -> str:
        return (
            "Searches for code symbol declarations (classes, functions, methods, interfaces) across the indexed repository. "
            "Returns declaration locations, line numbers, enclosing context headers, and implementation code snippets."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return SymbolSearchInput

    async def aexecute(self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any) -> ToolExecutionResult:
        sym_raw = kwargs.get("symbol_name", "")
        project_id_raw = kwargs.get("project_id")
        repository_id_raw = kwargs.get("repository_id")
        branch_id_raw = kwargs.get("branch_id")
        fpath_raw = kwargs.get("file_path_filter")
        limit_raw = kwargs.get("limit", 10)

        # 1. Validation
        symbol_name = validate_symbol_name(sym_raw)
        limit = validate_top_k(limit_raw, default=10, min_k=1, max_k=20)
        project_uuid = validate_uuid(project_id_raw, "project_id", required=True)
        assert project_uuid is not None
        repo_uuid = validate_uuid(repository_id_raw, "repository_id", required=False)
        branch_uuid = validate_uuid(branch_id_raw, "branch_id", required=False)

        path_filter: str | None = None
        if fpath_raw:
            path_filter = validate_safe_file_path(fpath_raw)

        # 2. Authorization & Active Index Verification
        await self.verify_project_access(user_id=user_id, project_id=project_uuid, db=db)
        active_ver = await self.get_active_index_version(
            project_id=project_uuid,
            repository_id=repo_uuid,
            branch_id=branch_uuid,
            db=db,
        )

        logger.info(
            f"[Tool:search_symbol] Looking up symbol '{symbol_name}' | "
            f"project={project_uuid} index_ver={active_ver.id} limit={limit}"
        )

        # 3. Query Indexed CodeChunk Symbols for Active Version
        stmt = (
            select(CodeChunk)
            .join(RepositoryFile, RepositoryFile.id == CodeChunk.file_id)
            .where(
                CodeChunk.index_version_id == active_ver.id,
                CodeChunk.symbol_name.ilike(f"%{symbol_name}%"),
            )
            .options(
                selectinload(CodeChunk.file),
                selectinload(CodeChunk.index_version).selectinload(RepositoryIndexVersion.branch),
            )
        )

        if path_filter:
            stmt = stmt.where(RepositoryFile.file_path.ilike(f"%{path_filter}%"))

        stmt = stmt.order_by(
            # Exact symbol matches first, then prefix/suffix
            CodeChunk.symbol_name == symbol_name,
            CodeChunk.start_line.asc(),
        ).limit(limit)

        res = await db.execute(stmt)
        chunks = res.scalars().all()

        formatted_symbols = []
        for c in chunks:
            branch_name = (
                c.index_version.branch.name
                if c.index_version and c.index_version.branch
                else ""
            )
            commit_sha = c.index_version.commit_sha if c.index_version else ""

            formatted_symbols.append(
                {
                    "symbol_name": c.symbol_name,
                    "chunk_type": c.chunk_type.value if hasattr(c.chunk_type, "value") else str(c.chunk_type),
                    "file_path": c.file.file_path if c.file else "",
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "context_header": c.context_header,
                    "content": truncate_tool_output(c.content, max_chars=4000),
                    "commit_sha": commit_sha,
                    "branch_name": branch_name,
                }
            )

        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={
                "symbol_query": symbol_name,
                "total_found": len(formatted_symbols),
                "symbols": formatted_symbols,
            },
        )
