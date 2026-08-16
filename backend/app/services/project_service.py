import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.models.auth import Membership
from app.models.project import Project
from app.schemas.project import ProjectCreate


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _verify_org_access(self, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        stmt = select(Membership).where(
            Membership.user_id == user_id, Membership.organization_id == org_id
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def list_for_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> list[Project]:
        if not await self._verify_org_access(user_id, org_id):
            raise ForbiddenException("You do not have access to this organization.")

        stmt = select(Project).where(Project.organization_id == org_id).order_by(Project.created_at.desc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_by_id(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project | None:
        stmt = select(Project).where(Project.id == project_id)
        res = await self.db.execute(stmt)
        project = res.scalar_one_or_none()
        if not project:
            return None
        if not await self._verify_org_access(user_id, project.organization_id):
            raise ForbiddenException("You do not have access to this project.")
        return project

    async def create(self, user_id: uuid.UUID, data: ProjectCreate) -> Project:
        if not await self._verify_org_access(user_id, data.organization_id):
            raise ForbiddenException("You do not have permission to create projects in this organization.")

        project = Project(
            organization_id=data.organization_id,
            name=data.name,
            description=data.description,
            settings=data.settings or {},
        )
        self.db.add(project)
        await self.db.flush()
        return project
