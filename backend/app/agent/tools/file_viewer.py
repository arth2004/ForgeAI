import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.agent.tools.limits import MAX_FILE_CHARS, truncate_tool_output
from app.agent.tools.validation import (
    ToolValidationError,
    validate_safe_file_path,
    validate_uuid,
)
from app.models.codebase import RepositoryFile, RepositoryIndexVersion

logger = logging.getLogger(__name__)


class FileViewerInput(BaseModel):
    """Input parameters for the repository file viewer tool."""

    file_path: str = Field(
        ...,
        description="Relative repository path of the file to inspect (e.g. 'backend/app/core/config.py').",
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
    start_line: int | None = Field(
        default=None,
        description="Optional 1-indexed start line number to inspect a specific line window.",
    )
    end_line: int | None = Field(
        default=None,
        description="Optional 1-indexed end line number to inspect a specific line window.",
    )


class FileViewerTool(BaseRepositoryTool):
    """Tool retrieving indexed file contents and parsed structure from the active repository index."""

    @property
    def name(self) -> str:
        return "get_file"

    @property
    def description(self) -> str:
        return (
            "Retrieves full or windowed file contents and symbol structure from the active indexed repository. "
            "Returns file metadata (language, size, chunk count) and clean source code content."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return FileViewerInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        fpath_raw = kwargs.get("file_path", "")
        project_id_raw = kwargs.get("project_id")
        repository_id_raw = kwargs.get("repository_id")
        branch_id_raw = kwargs.get("branch_id")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        # 1. Validation
        file_path = validate_safe_file_path(fpath_raw)
        project_uuid = validate_uuid(project_id_raw, "project_id", required=True)
        assert project_uuid is not None
        repo_uuid = validate_uuid(repository_id_raw, "repository_id", required=False)
        branch_uuid = validate_uuid(branch_id_raw, "branch_id", required=False)

        if start_line is not None and start_line < 1:
            raise ToolValidationError(
                "start_line must be greater than or equal to 1.", field_name="start_line"
            )
        if end_line is not None and end_line < 1:
            raise ToolValidationError(
                "end_line must be greater than or equal to 1.", field_name="end_line"
            )
        if start_line is not None and end_line is not None and start_line > end_line:
            raise ToolValidationError(
                "start_line cannot be greater than end_line.", field_name="start_line"
            )

        # 2. Authorization & Active Index Verification
        await self.verify_project_access(user_id=user_id, project_id=project_uuid, db=db)
        active_ver = await self.get_active_index_version(
            project_id=project_uuid,
            repository_id=repo_uuid,
            branch_id=branch_uuid,
            db=db,
        )

        logger.info(
            f"[Tool:get_file] Retrieving file '{file_path}' | "
            f"project={project_uuid} index_ver={active_ver.id}"
        )

        # 3. Query RepositoryFile with chunks
        stmt = (
            select(RepositoryFile)
            .where(
                RepositoryFile.index_version_id == active_ver.id,
                RepositoryFile.file_path == file_path,
            )
            .options(
                selectinload(RepositoryFile.chunks),
                selectinload(RepositoryFile.index_version).selectinload(
                    RepositoryIndexVersion.branch
                ),
            )
        )
        file_obj = (await db.execute(stmt)).scalars().first()

        if not file_obj:
            # Check if file exists under similar path for helpful diagnostic
            fuzzy_stmt = (
                select(RepositoryFile.file_path)
                .where(
                    RepositoryFile.index_version_id == active_ver.id,
                    RepositoryFile.file_path.ilike(f"%{file_path}%"),
                )
                .limit(5)
            )
            similar_files = (await db.execute(fuzzy_stmt)).scalars().all()
            suggestion_msg = f" Did you mean: {similar_files}?" if similar_files else ""

            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=f"File '{file_path}' not found in active repository index.{suggestion_msg}",
            )

        # 4. Assemble and slice content
        sorted_chunks = sorted(file_obj.chunks, key=lambda c: c.start_line)

        # Collect chunk summaries
        chunk_summaries = [
            {
                "symbol_name": c.symbol_name,
                "chunk_type": c.chunk_type.value
                if hasattr(c.chunk_type, "value")
                else str(c.chunk_type),
                "start_line": c.start_line,
                "end_line": c.end_line,
                "context_header": c.context_header,
            }
            for c in sorted_chunks
        ]

        # Combine text content
        assembled_content = "\n\n".join(c.content for c in sorted_chunks)

        if start_line is not None or end_line is not None:
            # Line-window filtering
            lines = assembled_content.splitlines()
            s_idx = (start_line - 1) if start_line is not None else 0
            e_idx = end_line if end_line is not None else len(lines)
            selected_lines = lines[s_idx:e_idx]
            output_content = "\n".join(selected_lines)
            actual_line_range = f"{s_idx + 1}-{min(e_idx, len(lines))}"
        else:
            output_content = assembled_content
            actual_line_range = f"1-{len(assembled_content.splitlines())}"

        truncated_content = truncate_tool_output(output_content, max_chars=MAX_FILE_CHARS)

        branch_name = (
            file_obj.index_version.branch.name
            if file_obj.index_version and file_obj.index_version.branch
            else ""
        )
        commit_sha = file_obj.index_version.commit_sha if file_obj.index_version else ""

        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={
                "file_path": file_obj.file_path,
                "language": file_obj.language,
                "size_bytes": file_obj.size_bytes,
                "content_hash": file_obj.content_hash,
                "total_chunks": len(sorted_chunks),
                "line_range": actual_line_range,
                "chunks": chunk_summaries,
                "content": truncated_content,
                "commit_sha": commit_sha,
                "branch_name": branch_name,
            },
        )
