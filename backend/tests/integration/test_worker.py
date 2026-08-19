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


@pytest.mark.asyncio
async def test_index_repository_task_execution():
    """Verifies that index_repository_task delegates to IngestionEngine.run_indexing with correct arguments."""
    import uuid

    from app.workers.ingestion_tasks import index_repository_task

    repo_id = str(uuid.uuid4())
    branch_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    expected_version_id = uuid.uuid4()

    ctx = {}

    with patch("app.services.ingestion.engine.IngestionEngine.run_indexing", new_callable=AsyncMock) as mock_engine:
        mock_engine.return_value = expected_version_id

        result = await index_repository_task(
            ctx=ctx,
            repository_id=repo_id,
            branch_id=branch_id,
            is_full_reindex=True,
            job_id=job_id,
        )

        assert result["status"] == "completed"
        assert result["repository_id"] == repo_id
        assert result["branch_id"] == branch_id
        assert result["index_version_id"] == str(expected_version_id)

        mock_engine.assert_called_once_with(
            repository_id=uuid.UUID(repo_id),
            branch_id=uuid.UUID(branch_id),
            is_full_reindex=True,
            job_id=uuid.UUID(job_id),
        )

