import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth import Membership, Organization, Role, User
from app.schemas.auth import TokenResponse, UserLogin, UserRegister


def _generate_slug(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "org"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower().strip())
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id).options(selectinload(User.memberships))
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def register(self, data: UserRegister) -> tuple[User, TokenResponse]:
        existing = await self.get_user_by_email(data.email)
        if existing:
            raise ConflictException("User with this email already exists.")

        hashed_pw = hash_password(data.password)
        user = User(
            email=data.email.lower().strip(),
            hashed_password=hashed_pw,
            full_name=data.full_name,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()

        # If org name specified (or default derived from email), create initial organization & owner membership
        org_name = data.organization_name or f"{data.full_name or data.email.split('@')[0]}'s Org"
        base_slug = _generate_slug(org_name)
        slug = f"{base_slug}-{str(uuid.uuid4())[:8]}"

        org = Organization(
            name=org_name,
            slug=slug,
        )
        self.db.add(org)
        await self.db.flush()

        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role=Role.owner,
        )
        self.db.add(membership)
        await self.db.flush()

        token = create_access_token(subject=str(user.id))
        token_resp = TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        return user, token_resp

    async def login(self, data: UserLogin) -> tuple[User, TokenResponse]:
        user = await self.get_user_by_email(data.email)
        if not user or not user.hashed_password:
            raise UnauthorizedException("Invalid email or password.")

        if not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password.")

        if not user.is_active:
            raise UnauthorizedException("User account is inactive.")

        token = create_access_token(subject=str(user.id))
        token_resp = TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        return user, token_resp
