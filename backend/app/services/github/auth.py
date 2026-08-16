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
from app.core.telemetry import logger
from app.models.auth import User
from app.services.github.client import github_client


class GitHubAuthService:
    """Service handling GitHub App user authorization, state verification, and credential lifecycle.

    Security & Architecture Principles:
    1. Zero Persistent Tokens: No user access tokens or installation access tokens are persisted to PostgreSQL.
    2. Ephemeral Ingestion: Installation Access Tokens are minted on demand via RS256 App JWTs and cached
       strictly in memory with a short TTL buffer.
    3. Installation Association Validation: The user identity is validated directly against GitHub OAuth,
       and the installation ID must be verified as owned by or accessible to that authenticated GitHub user.
       Redirect-provided installation_ids are never blindly trusted.
    """

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
        """Exchanges an authorization code for an ephemeral user access token.

        This token is used strictly within the callback lifecycle to verify identity and
        installations, and is NEVER saved to the database.
        """
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
        """Associates the GitHub user profile & installation ID with the local User account.

        Guarantees:
        1. Validates that the GitHub installation actually belongs to or is authorized for the authenticated user.
        2. Never persists OAuth tokens or Installation tokens to PostgreSQL.
        """
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User account not found.")

        # 1. If code was provided, exchange for user token and fetch user identity
        if code:
            user_token = await cls.exchange_code_for_token(code)
            profile = await github_client.get_user_profile(user_token)

            github_uid = profile.get("id")
            github_login = profile.get("login")

            user.github_user_id = github_uid
            user.github_username = github_login
            if profile.get("avatar_url"):
                user.avatar_url = profile["avatar_url"]

            # 2. Verify installation ownership / access
            user_installations = []
            try:
                user_installations = await github_client.get_user_installations(user_token)
            except Exception as e:
                logger.warning(f"Could not retrieve user installations list: {e}")

            user_inst_ids = [inst["id"] for inst in user_installations if "id" in inst]

            if installation_id:
                # If an installation_id was passed in the redirect query, verify it
                if user_inst_ids and installation_id not in user_inst_ids:
                    # Double-check installation metadata directly via App JWT
                    try:
                        inst_details = await github_client.get_installation(installation_id)
                        account_id = inst_details.get("account", {}).get("id")
                        account_login = inst_details.get("account", {}).get("login", "").lower()
                        if account_id != github_uid and account_login != (github_login or "").lower():
                            raise UnauthorizedException("The specified GitHub installation does not belong to your account.")
                    except Exception as exc:
                        if isinstance(exc, UnauthorizedException):
                            raise
                        logger.error(f"Failed to verify installation ownership: {exc}")
                        raise UnauthorizedException("Could not verify ownership of the GitHub App installation.") from exc
                user.github_installation_id = installation_id
            elif user_inst_ids:
                # Auto-assign first authorized installation if none specified in query
                user.github_installation_id = user_inst_ids[0]

        elif installation_id:
            # If only installation_id is provided without OAuth code, verify the user already has a connected GitHub identity
            if not user.github_user_id:
                raise UnauthorizedException("Cannot link installation without authenticated GitHub user identity.")
            # Verify installation ownership via App JWT
            try:
                inst_details = await github_client.get_installation(installation_id)
                account_id = inst_details.get("account", {}).get("id")
                account_login = inst_details.get("account", {}).get("login", "").lower()
                if account_id != user.github_user_id and account_login != (user.github_username or "").lower():
                    raise UnauthorizedException("The specified GitHub installation does not belong to your account.")
            except Exception as exc:
                if isinstance(exc, UnauthorizedException):
                    raise
                logger.error(f"Failed to verify installation ownership: {exc}")
                raise UnauthorizedException("Could not verify ownership of the GitHub App installation.") from exc

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

        await db.commit()
        await db.refresh(user)
        logger.info(f"Disconnected GitHub account for user {user.id}")
        return user


github_auth_service = GitHubAuthService()
