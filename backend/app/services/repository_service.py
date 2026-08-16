import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ForbiddenException
from app.models.auth import Membership
from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch
from app.schemas.repository import RepositoryCreate


class RepositoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _verify_project_access(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        stmt = (
            select(Project)
            .join(Membership, Membership.organization_id == Project.organization_id)
            .where(Project.id == project_id, Membership.user_id == user_id)
        )
        res = await self.db.execute(stmt)
        project = res.scalar_one_or_none()
        if not project:
            raise ForbiddenException("You do not have access to this project.")
        return project

    async def list_for_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> list[Repository]:
        await self._verify_project_access(user_id, project_id)
        stmt = (
            select(Repository)
            .where(Repository.project_id == project_id)
            .order_by(Repository.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_by_id(self, user_id: uuid.UUID, repo_id: uuid.UUID) -> Repository | None:
        stmt = select(Repository).where(Repository.id == repo_id)
        res = await self.db.execute(stmt)
        repo = res.scalar_one_or_none()
        if not repo:
            return None
        await self._verify_project_access(user_id, repo.project_id)
        return repo

    async def create(self, user_id: uuid.UUID, data: RepositoryCreate) -> Repository:
        await self._verify_project_access(user_id, data.project_id)

        # Check for duplicate repo full_name within project
        stmt = select(Repository).where(
            Repository.project_id == data.project_id,
            Repository.full_name == data.full_name,
        )
        existing = await self.db.execute(stmt)
        if existing.scalar_one_or_none():
            raise ConflictException(f"Repository '{data.full_name}' is already connected to this project.")

        repo = Repository(
            project_id=data.project_id,
            github_repo_id=data.github_repo_id,
            full_name=data.full_name,
            default_branch=data.default_branch,
            is_private=data.is_private,
            indexing_status=IndexingStatus.pending,
        )
        self.db.add(repo)
        await self.db.flush()

        # Create default branch entry
        default_branch = RepositoryBranch(
            repository_id=repo.id,
            name=data.default_branch,
        )
        self.db.add(default_branch)
        await self.db.flush()

        return repo
