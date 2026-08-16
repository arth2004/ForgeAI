from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_healthy(client: AsyncClient):
    with patch("app.api.v1.health.check_database_connection", new_callable=AsyncMock) as mock_db, \
         patch("app.api.v1.health.check_redis_connection", new_callable=AsyncMock) as mock_redis, \
         patch("app.api.v1.health.get_arq_pool", new_callable=AsyncMock) as mock_arq:

        mock_db.return_value = True
        mock_redis.return_value = True
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_arq.return_value = mock_pool

        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["services"]["database"] == "ok"
        assert data["services"]["redis"] == "ok"
        assert data["services"]["worker_queue"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint_degraded(client: AsyncClient):
    with patch("app.api.v1.health.check_database_connection", new_callable=AsyncMock) as mock_db, \
         patch("app.api.v1.health.check_redis_connection", new_callable=AsyncMock) as mock_redis, \
         patch("app.api.v1.health.get_arq_pool", new_callable=AsyncMock) as mock_arq:

        mock_db.return_value = False
        mock_redis.return_value = True
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_arq.return_value = mock_pool

        response = await client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["database"] == "down"
