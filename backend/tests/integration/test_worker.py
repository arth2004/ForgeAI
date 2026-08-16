from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.workers.health_tasks import health_check_job


@pytest.mark.asyncio
async def test_health_check_job_direct_execution():
    ctx = {}
    payload = {"task": "ping", "sequence": 42}
    result = await health_check_job(ctx, payload)

    assert result["status"] == "success"
    assert result["input_payload"] == payload
    assert "processed_at" in result
    assert result["worker_name"] == "ForgeAI-ARQ-Worker"


@pytest.mark.asyncio
async def test_worker_api_endpoints(client: AsyncClient):
    with patch("app.api.v1.worker.get_arq_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_arq = AsyncMock()
        mock_job = AsyncMock()
        mock_job.job_id = "test-job-uuid-123"
        mock_arq.enqueue_job.return_value = mock_job
        mock_get_pool.return_value = mock_arq

        # 1. Enqueue job
        resp = await client.post("/api/v1/worker/test-job", json={"message": "hello-arq"})
        assert resp.status_code == 202
        assert resp.json()["job_id"] == "test-job-uuid-123"
        assert resp.json()["status"] == "queued"
