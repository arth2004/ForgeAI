from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import EmbeddingQuotaExhaustedException, ForgeAIException
from app.services.embedding.factory import get_embedding_provider
from app.services.embedding.gemini import (
    GeminiEmbeddingProvider,
    is_daily_or_project_quota_exhaustion,
    parse_retry_delay,
    sanitize_error,
)
from app.services.embedding.openai import OpenAIEmbeddingProvider


def test_embedding_factory_defaults():
    provider = get_embedding_provider("google")
    assert isinstance(provider, GeminiEmbeddingProvider)
    assert provider.provider_name == "google"
    assert provider.model_name == "gemini-embedding-2"
    assert provider.dimension == 768
    assert provider.version == 1

    openai_provider = get_embedding_provider("openai")
    assert isinstance(openai_provider, OpenAIEmbeddingProvider)
    assert openai_provider.provider_name == "openai"


@pytest.mark.asyncio
async def test_gemini_embed_documents_batching(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_key_123")
    provider = GeminiEmbeddingProvider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "embeddings": [
            {"values": [0.1] * 768},
            {"values": [0.2] * 768},
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        vectors = await provider.embed_documents(["chunk 1", "chunk 2"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 768
        assert vectors[0][0] == 0.1
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_embed_query(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_key_123")
    provider = GeminiEmbeddingProvider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embeddings": [{"values": [0.5] * 768}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        vector = await provider.embed_query("find authentication service")

        assert len(vector) == 768
        assert vector[0] == 0.5


@pytest.mark.asyncio
async def test_gemini_temporary_429_retries_and_succeeds(monkeypatch):
    """Temporary 429 rate limit is retried with backoff and succeeds on subsequent attempt."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_key_123")
    provider = GeminiEmbeddingProvider()

    # First attempt returns temporary 429 with retryDelay; second attempt succeeds
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = httpx.Headers({"Retry-After": "1"})
    resp_429.json.return_value = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "Temporary rate limit exceeded.",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "metadata": {
                        "quota_metric": "generativelanguage.googleapis.com/embed_content_requests_per_minute"
                    },
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "0.1s"},
            ],
        }
    }

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"embeddings": [{"values": [0.3] * 768}]}

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_post.side_effect = [resp_429, resp_200]

        vectors = await provider.embed_documents(["test chunk"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_daily_quota_exhaustion_fails_immediately_no_repeated_retries(monkeypatch):
    """Daily/project quota exhaustion raises EmbeddingQuotaExhaustedException immediately on first attempt without 4 retries."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_key_123")
    provider = GeminiEmbeddingProvider()

    resp_daily_quota = MagicMock()
    resp_daily_quota.status_code = 429
    resp_daily_quota.json.return_value = {
        "error": {
            "code": 429,
            "message": "Resource has been exhausted (e.g. check quota).",
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "domain": "googleapis.com",
                    "metadata": {
                        "consumer": "projects/123456",
                        "quota_metric": "generativelanguage.googleapis.com/embed_content_free_tier_requests",
                        "quota_id": "EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier",
                    },
                }
            ],
        }
    }

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_post.return_value = resp_daily_quota

        with pytest.raises(EmbeddingQuotaExhaustedException) as exc_info:
            await provider.embed_documents(["test chunk"])

        assert "Gemini embedding quota exhausted" in str(exc_info.value)
        # Verify it did NOT retry 4 times: only called ONCE
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()


def test_retry_delay_parser_and_quota_detector():
    """Helper tests for retry delay extraction and quota metric detection."""
    # Test retryDelay string
    data_with_delay = {
        "error": {
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "25.5s"}]
        }
    }
    assert parse_retry_delay(data_with_delay, httpx.Headers()) == 25.5

    # Test daily quota metric
    daily_quota_data = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "metadata": {
                        "quota_metric": "generativelanguage.googleapis.com/embed_content_free_tier_requests",
                        "quota_id": "EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier",
                    },
                }
            ],
        }
    }
    assert is_daily_or_project_quota_exhaustion(daily_quota_data, 429) is True

    # Test temporary RPM metric is NOT daily quota
    rpm_data = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "metadata": {
                        "quota_metric": "generativelanguage.googleapis.com/embed_content_requests_per_minute"
                    },
                }
            ],
        }
    }
    assert is_daily_or_project_quota_exhaustion(rpm_data, 429) is False


def test_sanitize_error_redacts_api_keys():
    """Verify that error messages and URLs redact API keys and secrets."""
    raw_error = "Failed request to https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:batchEmbedContents?key=AIzaSyD_secret12345 with status 429"
    sanitized = sanitize_error(raw_error, "AIzaSyD_secret12345")

    assert "AIzaSyD_secret12345" not in sanitized
    assert "[REDACTED" in sanitized
