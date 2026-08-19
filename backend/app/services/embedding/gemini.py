import asyncio
import logging
import random
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import EmbeddingQuotaExhaustedException, ForgeAIException
from app.services.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)


def parse_retry_delay(response_data: dict[str, Any], headers: httpx.Headers | dict[str, str] | None = None) -> float | None:
    """Extracts suggested retry delay in seconds from Gemini error details or HTTP headers."""
    # 1. Check Retry-After header
    if headers:
        retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
        if retry_after:
            try:
                val = float(retry_after)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass

    # 2. Check details in error payload
    error = response_data.get("error", {})
    details = error.get("details", [])
    for detail in details:
        if isinstance(detail, dict):
            # Check RetryInfo
            if detail.get("@type", "").endswith("RetryInfo") or "retryDelay" in detail:
                raw_delay = detail.get("retryDelay")
                if isinstance(raw_delay, str) and raw_delay.endswith("s"):
                    try:
                        return float(raw_delay[:-1])
                    except ValueError:
                        pass
                elif isinstance(raw_delay, (int, float)):
                    return float(raw_delay)

    return None


def is_daily_or_project_quota_exhaustion(response_data: dict[str, Any], status_code: int) -> bool:
    """Determines whether a 429 response indicates permanent daily/project quota exhaustion rather than a transient burst limit."""
    if status_code != 429:
        return False

    error = response_data.get("error", {})
    err_message = str(error.get("message", ""))
    err_status = str(error.get("status", ""))
    details = error.get("details", [])

    text_corpus = f"{err_message} {err_status}".lower()
    if "perday" in text_corpus or "per_day" in text_corpus or "daily" in text_corpus:
        return True

    for detail in details:
        if not isinstance(detail, dict):
            continue

        # Inspect ErrorInfo metadata
        metadata = detail.get("metadata", {})
        quota_metric = str(metadata.get("quota_metric", "")).lower()
        quota_id = str(metadata.get("quota_id", "")).lower()

        if any(term in quota_metric for term in ("perday", "per_day", "daily", "free_tier_requests")):
            if "minute" not in quota_metric:
                return True
        if any(term in quota_id for term in ("perday", "per_day", "daily", "freetier")):
            if "minute" not in quota_id:
                return True

        # Inspect QuotaFailure violations
        violations = detail.get("violations", [])
        for v in violations:
            if isinstance(v, dict):
                desc = str(v.get("description", "")).lower()
                if "daily" in desc or "per day" in desc or "quota limit" in desc:
                    return True

        # If retry delay is >= 300s (5 minutes), treat as daily/long-term quota
        raw_delay = detail.get("retryDelay")
        if isinstance(raw_delay, str) and raw_delay.endswith("s"):
            try:
                if float(raw_delay[:-1]) >= 300.0:
                    return True
            except ValueError:
                pass

    return False


def sanitize_error(text: str, api_key: str | None = None) -> str:
    """Redacts API keys and secrets from error messages and logs."""
    if not text:
        return ""
    cleaned = str(text)
    if api_key:
        cleaned = cleaned.replace(api_key, "[REDACTED_API_KEY]")
    cleaned = re.sub(r"key=([A-Za-z0-9_\-\.]+)", "key=[REDACTED]", cleaned)
    cleaned = re.sub(r'key":\s*"([^"]+)"', 'key": "[REDACTED]"', cleaned)
    return cleaned


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embedding provider using gemini-embedding-2 with 768 dimensions."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ) -> None:
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_EMBEDDING_MODEL
        self._dimension = dimension or settings.GEMINI_EMBEDDING_DIMENSION

    @property
    def provider_name(self) -> str:
        return "google"

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
        """Embeds a list of document chunks using dynamic sub-batches and retry backoff."""
        if not texts:
            return []

        if not self._api_key:
            raise ForgeAIException("GEMINI_API_KEY is not configured.", status_code=500)

        results: list[list[float]] = []
        batch_size = min(settings.MAX_CHUNKS_PER_EMBED_BATCH, 100)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_embeddings = await self._embed_batch_with_retry(
                    batch, task_type="RETRIEVAL_DOCUMENT", client=client
                )
                results.extend(batch_embeddings)

        return results

    async def embed_query(self, text: str) -> list[float]:
        """Embeds a single search query."""
        if not text:
            return [0.0] * self._dimension

        if not self._api_key:
            raise ForgeAIException("GEMINI_API_KEY is not configured.", status_code=500)

        batch_embeddings = await self._embed_batch_with_retry([text], task_type="RETRIEVAL_QUERY")
        if not batch_embeddings:
            raise ForgeAIException(
                "Failed to generate query embedding from Gemini.", status_code=502
            )
        return batch_embeddings[0]

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        max_retries: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> list[list[float]]:
        url = f"{self.BASE_URL}/models/{self._model}:batchEmbedContents?key={self._api_key}"

        requests_payload: list[dict[str, Any]] = [
            {
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": self._dimension,
            }
            for t in texts
        ]

        payload = {"requests": requests_payload}

        for attempt in range(max_retries):
            try:
                if client is not None:
                    response = await client.post(url, json=payload)
                else:
                    async with httpx.AsyncClient(timeout=30.0) as local_client:
                        response = await local_client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    raw_embeddings = data.get("embeddings", [])
                    return [e.get("values", []) for e in raw_embeddings]

                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = {}

                # 1. Check for daily / project quota exhaustion (immediate fail, NO repeated retries)
                if is_daily_or_project_quota_exhaustion(resp_data, response.status_code):
                    logger.error(
                        "Gemini daily/project embedding quota exhausted. Aborting retries immediately."
                    )
                    raise EmbeddingQuotaExhaustedException(
                        "Gemini embedding quota exhausted. Indexing can resume when the provider quota resets or billing/quota is increased.",
                        details={
                            "provider": "google",
                            "model": self._model,
                            "status_code": 429,
                            "quota_type": "daily_or_project_exhausted",
                        },
                    )

                # 2. Check for temporary rate limit (429) or transient 5xx errors
                elif response.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        parsed_delay = parse_retry_delay(resp_data, response.headers)
                        if parsed_delay is not None and 0.5 <= parsed_delay <= 60.0:
                            delay = parsed_delay + random.uniform(0.1, 0.5)
                        elif response.status_code == 429:
                            delay = min((2**attempt) * 5.0 + random.uniform(0.5, 2.0), 60.0)
                        else:
                            delay = min((2**attempt) + random.uniform(0.1, 0.5), 30.0)

                        logger.warning(
                            f"Gemini embedding rate limit / error ({response.status_code}). "
                            f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        safe_msg = sanitize_error(response.text, self._api_key)
                        raise ForgeAIException(
                            f"Gemini embedding API rate limit/error exceeded after {max_retries} attempts: {safe_msg}",
                            status_code=502,
                        )
                else:
                    safe_msg = sanitize_error(response.text, self._api_key)
                    raise ForgeAIException(
                        f"Gemini embedding API error ({response.status_code}): {safe_msg}",
                        status_code=502,
                    )

            except httpx.RequestError as exc:
                if attempt < max_retries - 1:
                    delay = (2**attempt) + random.uniform(0.1, 0.5)
                    await asyncio.sleep(delay)
                    continue
                safe_exc = sanitize_error(str(exc), self._api_key)
                raise ForgeAIException(
                    f"Network error calling Gemini embedding API: {safe_exc}", status_code=502
                ) from exc

        return []
