from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract Base Class for multi-provider code embeddings."""

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generates embedding vectors for a batch of text chunks."""
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generates an embedding vector for a single search query."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g. 'google', 'openai')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name (e.g. 'gemini-embedding-2', 'text-embedding-3-small')."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality (e.g. 768)."""
        pass

    @property
    @abstractmethod
    def version(self) -> int:
        """Embedding version integer for migration tracking."""
        pass
