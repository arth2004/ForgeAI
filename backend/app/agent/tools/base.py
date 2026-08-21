import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.validation import RepositoryNotIndexedError, ToolAuthorizationError
from app.models.auth import Membership
from app.models.codebase import IndexVersionStatus, RepositoryIndexVersion
from app.models.project import Project, Repository

logger = logging.getLogger(__name__)


class ToolExecutionResult(BaseModel):
    """Standardized structured output returned by all repository agent tools."""

    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None


class BaseRepositoryTool(ABC):
    """Abstract base class for all repository intelligence agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name for the tool (e.g. 'search_repository')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed functional description exposed to LLMs for tool selection."""
        ...

    @property
    @abstractmethod
    def args_schema(self) -> type[BaseModel]:
        """Pydantic model validating input parameters."""
        ...

    @abstractmethod
    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        """Executes the tool with validated arguments and authorization context."""
        ...

    async def verify_project_access(
        self, user_id: uuid.UUID, project_id: uuid.UUID, db: AsyncSession
    ) -> Project:
        """Verifies that the user belongs to the project's organization (tenant isolation)."""
        stmt = (
            select(Project)
            .join(Membership, Membership.organization_id == Project.organization_id)
            .where(Project.id == project_id, Membership.user_id == user_id)
        )
        res = await db.execute(stmt)
        project = res.scalar_one_or_none()
        if not project:
            raise ToolAuthorizationError(
                f"User does not have authorization to access project '{project_id}'."
            )
        return project

    async def get_active_index_version(
        self,
        project_id: uuid.UUID,
        db: AsyncSession,
        repository_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> RepositoryIndexVersion:
        """Verifies that an ACTIVE index version exists for the requested project/repository/branch."""
        stmt = (
            select(RepositoryIndexVersion)
            .join(Repository, Repository.id == RepositoryIndexVersion.repository_id)
            .where(
                Repository.project_id == project_id,
                RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
            )
        )
        if repository_id:
            stmt = stmt.where(RepositoryIndexVersion.repository_id == repository_id)
        if branch_id:
            stmt = stmt.where(RepositoryIndexVersion.branch_id == branch_id)

        stmt = stmt.order_by(RepositoryIndexVersion.created_at.desc()).limit(1)
        res = await db.execute(stmt)
        active_ver = res.scalar_one_or_none()

        if not active_ver:
            raise RepositoryNotIndexedError(
                f"No ACTIVE index version found for project '{project_id}' "
                f"(repository_id={repository_id}, branch_id={branch_id}). "
                f"Repository indexing must complete before context can be retrieved."
            )
        return active_ver
