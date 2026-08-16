import asyncio
import os
import time
from datetime import datetime
from typing import Any

import httpx
import jwt

from app.core.config import settings
from app.core.exceptions import ForbiddenException, NotFoundException, UnauthorizedException
from app.core.telemetry import logger


class GitHubRateLimitError(ForbiddenException):
    """Raised when GitHub API rate limits are exceeded."""
    def __init__(self, message: str = "GitHub API rate limit exceeded. Please try again later."):
        super().__init__(message)


class GitHubApiError(Exception):
    """Generic GitHub API failure."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"GitHub API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message


class GitHubClient:
    """Typed asynchronous client for GitHub App and REST APIs."""

    BASE_URL = "https://api.github.com"

    def __init__(self) -> None:
        self._token_cache: dict[str, tuple[str, float]] = {}  # key -> (token, expiry_timestamp)

    def _get_private_key(self) -> str:
        """Retrieves GitHub App private key from configuration or file."""
        if settings.GITHUB_PRIVATE_KEY:
            return settings.GITHUB_PRIVATE_KEY

        if settings.GITHUB_PRIVATE_KEY_PATH and os.path.exists(settings.GITHUB_PRIVATE_KEY_PATH):
            with open(settings.GITHUB_PRIVATE_KEY_PATH, encoding="utf-8") as f:
                return f.read()

        return ""

    def generate_app_jwt(self) -> str:
        """Generates an RS256 JWT for GitHub App authentication (valid for 10 minutes)."""
        key_pem = self._get_private_key()
        if not key_pem or not settings.GITHUB_APP_ID:
            raise UnauthorizedException("GitHub App credentials (APP_ID or Private Key) are not configured.")

        now = int(time.time())
        payload = {
            "iat": now - 60,  # 1 minute clock skew allowance
            "exp": now + (9 * 60),  # 9 minutes expiration
            "iss": str(settings.GITHUB_APP_ID),
        }

        return jwt.encode(payload, key=key_pem, algorithm="RS256")

    async def get_installation_access_token(
        self,
        installation_id: int,
        repository_ids: list[int] | None = None,
    ) -> str:
        """Generates or retrieves a short-lived Installation Access Token (1 hour TTL).

        Supports optional repository-level scoping. Tokens are cached in-memory strictly
        for up to 50 minutes and never persisted as durable database records.
        """
        cache_key = f"inst_{installation_id}_{sorted(repository_ids) if repository_ids else 'all'}"
        now = time.time()

        if cache_key in self._token_cache:
            token, expiry = self._token_cache[cache_key]
            if now < expiry - 300:  # 5 minutes safety buffer
                return token

        app_jwt = self.generate_app_jwt()
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        body: dict[str, Any] = {}
        if repository_ids:
            body["repository_ids"] = repository_ids

        async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=15.0) as client:
            response = await client.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers=headers,
                json=body,
            )

            if response.status_code == 404:
                raise NotFoundException("GitHub App installation not found or access was revoked.")
            elif response.status_code == 401 or response.status_code == 403:
                raise UnauthorizedException("Failed to generate GitHub installation token. Check App permissions.")
            elif response.status_code != 201:
                raise GitHubApiError(response.status_code, "Failed to obtain installation token from GitHub.")

            data = response.json()
            token = data["token"]
            expires_at_str = data.get("expires_at")

            # Default TTL 3600 seconds (1 hour)
            expiry_timestamp = now + 3500
            if expires_at_str:
                try:
                    expiry_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    expiry_timestamp = expiry_dt.timestamp()
                except Exception:
                    pass

            self._token_cache[cache_key] = (token, expiry_timestamp)
            return token

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> httpx.Response:
        """Executes an authenticated GitHub API request with sanitized error handling."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=20.0) as client:
                    response = await client.request(
                        method=method,
                        url=path,
                        headers=headers,
                        params=params,
                        json=json_data,
                    )

                    # Handle Rate Limiting
                    if response.status_code == 403 and "rate limit" in response.text.lower():
                        reset_header = response.headers.get("x-ratelimit-reset")
                        if reset_header and attempt < retries:
                            wait_seconds = min(max(int(reset_header) - int(time.time()), 1), 5)
                            logger.warning(f"GitHub Rate Limit hit. Waiting {wait_seconds}s...")
                            await asyncio.sleep(wait_seconds)
                            continue
                        raise GitHubRateLimitError()

                    if response.status_code == 401:
                        raise UnauthorizedException("GitHub authentication failed. Please re-authenticate.")
                    elif response.status_code == 404:
                        raise NotFoundException("GitHub resource not found.")
                    elif response.status_code >= 400:
                        raise GitHubApiError(response.status_code, "GitHub API returned an error.")

                    return response

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt < retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                logger.error(f"GitHub API connection failure on {path}: {exc.__class__.__name__}")
                raise GitHubApiError(503, "GitHub API service is currently unavailable.") from exc

        raise GitHubApiError(500, "Failed to complete GitHub API request.")

    async def get_user_profile(self, user_access_token: str) -> dict[str, Any]:
        """Retrieves identity of the authenticated GitHub user."""
        response = await self._request("GET", "/user", token=user_access_token)
        return response.json()

    async def get_user_installations(self, user_access_token: str) -> list[dict[str, Any]]:
        """Lists GitHub App installations accessible to the authenticated user."""
        response = await self._request("GET", "/user/installations", token=user_access_token)
        return response.json().get("installations", [])

    async def list_installation_repositories(
        self,
        installation_id: int,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """Lists repositories explicitly granted to this GitHub App installation."""
        token = await self.get_installation_access_token(installation_id)
        params = {"page": page, "per_page": per_page}
        response = await self._request(
            "GET",
            "/installation/repositories",
            token=token,
            params=params,
        )
        return response.json()

    async def get_repository(
        self,
        installation_id: int,
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        """Gets detailed repository metadata."""
        token = await self.get_installation_access_token(installation_id)
        response = await self._request("GET", f"/repos/{owner}/{repo}", token=token)
        return response.json()

    async def list_repository_branches(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Lists branches for an authorized repository."""
        token = await self.get_installation_access_token(installation_id)
        params = {"page": page, "per_page": per_page}
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/branches",
            token=token,
            params=params,
        )
        return response.json()


github_client = GitHubClient()
