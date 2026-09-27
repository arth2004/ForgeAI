"""Unit tests for Phase 7C.1 Real Provider and RAG Stabilization.

Validates:
1. Groq & Gemini chat model provider initialization and defaults.
2. Gemini embedding model configuration and 768d dimension alignment.
3. embedContent (single query) vs batchEmbedContents (document batch) endpoint routing.
4. Proper HTTP failure propagation without mock fallback in production path.
5. Compatibility with ChunkEmbedding Vector(768) schema.
"""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app.agent.exceptions import ModelProviderException
from app.agent.models import (
    GeminiChatModelProvider,
    OpenAIChatModelProvider,
    get_chat_model_provider,
)
from app.core.config import settings
from app.models.codebase import ChunkEmbedding
from app.services.embedding.factory import get_embedding_provider
from app.services.embedding.gemini import GeminiEmbeddingProvider


def test_provider_defaults_configuration():
    """Verifies that default provider settings resolve to working production models."""
    assert settings.AGENT_DEFAULT_PROVIDER == "groq"
    assert settings.AGENT_GEMINI_MODEL == "gemini-3.1-flash-lite"
    assert settings.GEMINI_EMBEDDING_MODEL == "gemini-embedding-001"
    assert settings.GEMINI_EMBEDDING_DIMENSION == 768


def test_groq_provider_initialization():
    """Verifies that Groq provider resolves correctly with base URL and model."""
    provider = get_chat_model_provider("groq")
    assert isinstance(provider, OpenAIChatModelProvider)
    assert provider.provider_name == "groq"
    assert provider.model_name == settings.GROQ_MODEL
    assert provider._base_url == settings.GROQ_BASE_URL


def test_gemini_provider_initialization():
    """Verifies that Gemini provider resolves with non-zero quota default model."""
    provider = get_chat_model_provider("google")
    assert isinstance(provider, GeminiChatModelProvider)
    assert provider.provider_name == "google"
    assert provider.model_name == "gemini-3.1-flash-lite"


def test_gemini_embedding_provider_initialization():
    """Verifies Gemini embedding provider configures 768d space and gemini-embedding-001."""
    embed_provider = get_embedding_provider("google")
    assert isinstance(embed_provider, GeminiEmbeddingProvider)
    assert embed_provider.model_name == "gemini-embedding-001"
    assert embed_provider.dimension == 768


@pytest.mark.asyncio
async def test_gemini_embed_query_uses_embed_content_endpoint():
    """Verifies that embed_query calls the :embedContent single query endpoint with outputDimensionality=768."""
    provider = GeminiEmbeddingProvider(api_key="test-api-key", model="gemini-embedding-001", dimension=768)

    mock_response = httpx.Response(
        status_code=200,
        json={
            "embedding": {
                "values": [0.1] * 768
            }
        },
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=test-api-key")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        vec = await provider.embed_query("search authentication functions")

        assert len(vec) == 768
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        call_url = call_args[0][0]
        call_json = call_args[1]["json"]

        assert ":embedContent" in call_url
        assert call_json["model"] == "models/gemini-embedding-001"
        assert call_json["taskType"] == "RETRIEVAL_QUERY"
        assert call_json["outputDimensionality"] == 768
        assert call_json["content"]["parts"][0]["text"] == "search authentication functions"


@pytest.mark.asyncio
async def test_gemini_embed_documents_uses_batch_embed_endpoint():
    """Verifies that embed_documents calls :batchEmbedContents with batch requests."""
    provider = GeminiEmbeddingProvider(api_key="test-api-key", model="gemini-embedding-001", dimension=768)

    mock_response = httpx.Response(
        status_code=200,
        json={
            "embeddings": [
                {"values": [0.1] * 768},
                {"values": [0.2] * 768},
            ]
        },
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key=test-api-key")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        vecs = await provider.embed_documents(["doc chunk 1", "doc chunk 2"])

        assert len(vecs) == 2
        assert len(vecs[0]) == 768
        assert len(vecs[1]) == 768

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        call_url = call_args[0][0]
        call_json = call_args[1]["json"]

        assert ":batchEmbedContents" in call_url
        assert len(call_json["requests"]) == 2
        assert call_json["requests"][0]["outputDimensionality"] == 768
        assert call_json["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"


@pytest.mark.asyncio
async def test_groq_provider_propagates_http_429_without_silent_swallowing():
    """Verifies that provider rate limits / quota errors propagate as ModelProviderException."""
    provider = OpenAIChatModelProvider(
        api_key="mock-key",
        model_name="openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
        provider_label="groq",
    )

    mock_response = httpx.Response(
        status_code=429,
        text=json.dumps({"error": {"message": "Rate limit reached for model openai/gpt-oss-120b"}}),
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(ModelProviderException) as exc_info:
            await provider.ainvoke([HumanMessage(content="Hello")])

        assert exc_info.value.status_code == 429
        assert "Rate limit" in exc_info.value.message


def test_chunk_embedding_schema_dimension_invariant():
    """Verifies that ChunkEmbedding column vector dimension is 768."""
    emb_col = ChunkEmbedding.__table__.columns["embedding"]
    dim_col = ChunkEmbedding.__table__.columns["dimension"]

    assert emb_col.type.dim == 768
    assert dim_col.default.arg == 768
