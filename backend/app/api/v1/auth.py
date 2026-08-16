from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.auth import User
from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account with initial organization and return access token.
    Note: Full GitHub OAuth login/callback is planned for Phase 2.
    """
    auth_service = AuthService(db)
    _, token_resp = await auth_service.register(data)
    return token_resp


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email and password and return access token.
    """
    auth_service = AuthService(db)
    _, token_resp = await auth_service.login(data)
    return token_resp


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Get the profile of the currently authenticated user.
    """
    return current_user
