import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings
from app.services.github.client import GitHubClient, GitHubRateLimitError


@pytest.fixture
def dummy_rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem


def test_generate_app_jwt(dummy_rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY", dummy_rsa_key)

    client = GitHubClient()
    jwt_token = client.generate_app_jwt()

    assert isinstance(jwt_token, str)
    assert len(jwt_token.split(".")) == 3


@pytest.mark.asyncio
async def test_get_installation_access_token_with_repository_scoping(dummy_rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY", dummy_rsa_key)

    client = GitHubClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "token": "ghs_scoped_mock_token_12345",
        "expires_at": "2026-08-16T20:00:00Z",
        "repositories": [{"id": 9999}],
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # Request token with repository scoping
        token = await client.get_installation_access_token(
            installation_id=42,
            repository_ids=[9999],
        )

        assert token == "ghs_scoped_mock_token_12345"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"] == {"repository_ids": [9999]}


@pytest.mark.asyncio
async def test_github_rate_limit_error_handling(dummy_rsa_key, monkeypatch):
    client = GitHubClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "API rate limit exceeded for user"
    mock_resp.headers = {"x-ratelimit-reset": str(int(time.time()) + 10)}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_resp

        with pytest.raises(GitHubRateLimitError):
            await client._request("GET", "/test", token="ghs_test", retries=0)
