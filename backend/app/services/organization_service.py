import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Membership, Organization, Role
from app.schemas.organization import OrganizationCreate


def _generate_slug(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "org"


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        stmt = select(Organization).where(Organization.id == org_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[Organization]:
        stmt = (
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def create(self, user_id: uuid.UUID, data: OrganizationCreate) -> Organization:
        slug = data.slug or _generate_slug(data.name)
        # Ensure slug uniqueness
        stmt = select(Organization).where(Organization.slug == slug)
        existing = await self.db.execute(stmt)
        if existing.scalar_one_or_none():
            slug = f"{slug}-{str(uuid.uuid4())[:6]}"

        org = Organization(
            name=data.name,
            slug=slug,
        )
        self.db.add(org)
        await self.db.flush()

        membership = Membership(
            user_id=user_id,
            organization_id=org.id,
            role=Role.owner,
        )
        self.db.add(membership)
        await self.db.flush()
        return org
