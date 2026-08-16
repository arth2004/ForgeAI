import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, UnauthorizedException
from app.core.security import encrypt_secret
from app.core.telemetry import logger
from app.models.auth import User
from app.services.github.client import github_client


class GitHubAuthService:
    """Service handling GitHub App user authorization, state verification, and credential lifecycle."""

    STATE_EXPIRY_SECONDS = 600  # 10 minutes

    @classmethod
    def generate_state(cls, user_id: uuid.UUID) -> str:
        """Generates an HMAC-SHA256 signed state parameter to prevent CSRF attacks."""
        timestamp = int(time.time())
        nonce = uuid.uuid4().hex[:12]
        payload = f"{user_id}:{timestamp}:{nonce}"

        signature = hmac.new(
            settings.JWT_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"{payload}:{signature}"

    @classmethod
    def validate_state(cls, state: str) -> uuid.UUID:
        """Validates state signature and checks expiration."""
        try:
            parts = state.split(":")
            if len(parts) != 4:
                raise UnauthorizedException("Invalid OAuth state format.")

            user_id_str, timestamp_str, nonce, signature = parts
            payload = f"{user_id_str}:{timestamp_str}:{nonce}"

            expected_sig = hmac.new(
                settings.JWT_SECRET.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                raise UnauthorizedException("Invalid OAuth state signature.")

            created_at = int(timestamp_str)
            if time.time() - created_at > cls.STATE_EXPIRY_SECONDS:
                raise UnauthorizedException("OAuth state has expired. Please try connecting again.")

            return uuid.UUID(user_id_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"State validation error: {e}")
            raise UnauthorizedException("Invalid OAuth state.") from e

    @classmethod
    def get_authorization_url(cls, user_id: uuid.UUID) -> str:
        """Generates the GitHub App installation / authorization URL with signed state."""
        state = cls.generate_state(user_id)

        # If GitHub App slug is provided, route directly to the App installation page
        if settings.GITHUB_APP_SLUG and settings.GITHUB_APP_SLUG != "forge-ai-app":
            params = {"state": state}
            return f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?{urlencode(params)}"

        # Otherwise fallback to standard OAuth authorize URL
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    @classmethod
    async def exchange_code_for_token(cls, code: str) -> str:
        """Exchanges an authorization code for a user access token."""
        url = "https://github.com/login/oauth/access_token"
        headers = {"Accept": "application/json"}
        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise UnauthorizedException("Failed to exchange authorization code with GitHub.")

            data = response.json()
            if "error" in data:
                logger.error(f"GitHub OAuth token exchange error: {data.get('error_description', data['error'])}")
                raise UnauthorizedException(f"GitHub authorization failed: {data.get('error_description', data['error'])}")

            return data["access_token"]

    @classmethod
    async def connect_user_github(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        code: str | None = None,
        installation_id: int | None = None,
    ) -> User:
        """Associates the GitHub user profile & installation ID with the local User account."""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User account not found.")

        # 1. If code was provided, exchange for user token and fetch profile
        if code:
            user_token = await cls.exchange_code_for_token(code)
            profile = await github_client.get_user_profile(user_token)

            user.github_user_id = profile.get("id")
            user.github_username = profile.get("login")
            if profile.get("avatar_url"):
                user.avatar_url = profile["avatar_url"]

            # Store encrypted user token for fetching personal installations
            user.encrypted_github_token = encrypt_secret(user_token)

            # If user has an existing installation, resolve it
            try:
                installations = await github_client.get_user_installations(user_token)
                if installations and not installation_id:
                    installation_id = installations[0].get("id")
            except Exception as e:
                logger.warning(f"Could not auto-fetch user installations: {e}")

        # 2. Record installation ID if supplied via redirect or auto-discovery
        if installation_id:
            user.github_installation_id = installation_id

        await db.commit()
        await db.refresh(user)
        logger.info(f"Connected GitHub for user {user.id}: @{user.github_username} (installation: {user.github_installation_id})")
        return user

    @classmethod
    async def disconnect_user_github(cls, db: AsyncSession, user_id: uuid.UUID) -> User:
        """Disconnects GitHub account and wipes stored credentials."""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found.")

        user.github_user_id = None
        user.github_username = None
        user.github_installation_id = None
        user.encrypted_github_token = None

        await db.commit()
        await db.refresh(user)
        logger.info(f"Disconnected GitHub account for user {user.id}")
        return user


github_auth_service = GitHubAuthService()
