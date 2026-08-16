from app.core.config import settings
from app.services.embedding.base import EmbeddingProvider
from app.services.embedding.gemini import GeminiEmbeddingProvider
from app.services.embedding.openai import OpenAIEmbeddingProvider


def get_embedding_provider(provider_name: str | None = None) -> EmbeddingProvider:
    """Factory creating the active EmbeddingProvider instance."""
    provider = (provider_name or settings.EMBEDDING_PROVIDER).lower()

    if provider == "google":
        return GeminiEmbeddingProvider()
    elif provider == "openai":
        return OpenAIEmbeddingProvider()
    else:
        # Default to Google Gemini
        return GeminiEmbeddingProvider()
