import asyncio
import logging
import random

import httpx

from app.core.config import settings
from app.core.exceptions import ForgeAIException
from app.services.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider (e.g. text-embedding-3-small)."""

    BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ) -> None:
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = model or settings.OPENAI_EMBEDDING_MODEL
        self._dimension = dimension or settings.OPENAI_EMBEDDING_DIMENSION

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def version(self) -> int:
        return 1

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._api_key:
            raise ForgeAIException("OPENAI_API_KEY is not configured.", status_code=500)

        results: list[list[float]] = []
        batch_size = min(settings.MAX_CHUNKS_PER_EMBED_BATCH, 100)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_embeddings = await self._embed_batch_with_retry(batch, client=client)
                results.extend(batch_embeddings)

        return results

    async def embed_query(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dimension

        if not self._api_key:
            raise ForgeAIException("OPENAI_API_KEY is not configured.", status_code=500)

        batch_embeddings = await self._embed_batch_with_retry([text])
        if not batch_embeddings:
            raise ForgeAIException(
                "Failed to generate query embedding from OpenAI.", status_code=502
            )
        return batch_embeddings[0]

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        max_retries: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> list[list[float]]:
        url = f"{self.BASE_URL}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": texts,
            "dimensions": self._dimension,
        }

        for attempt in range(max_retries):
            try:
                if client is not None:
                    response = await client.post(url, headers=headers, json=payload)
                else:
                    async with httpx.AsyncClient(timeout=30.0) as local_client:
                        response = await local_client.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    raw_data = data.get("data", [])
                    return [item.get("embedding", []) for item in raw_data]

                elif response.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        delay = (2**attempt) + random.uniform(0.1, 0.5)
                        logger.warning(
                            f"OpenAI embedding rate limit / error ({response.status_code}). Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise ForgeAIException(
                            f"OpenAI embedding API rate limit/error exceeded after {max_retries} attempts: {response.text}",
                            status_code=502,
                        )
                else:
                    raise ForgeAIException(
                        f"OpenAI embedding API error ({response.status_code}): {response.text}",
                        status_code=502,
                    )

            except httpx.RequestError as exc:
                if attempt < max_retries - 1:
                    delay = (2**attempt) + random.uniform(0.1, 0.5)
                    await asyncio.sleep(delay)
                    continue
                raise ForgeAIException(
                    f"Network error calling OpenAI embedding API: {str(exc)}", status_code=502
                ) from exc

        return []
