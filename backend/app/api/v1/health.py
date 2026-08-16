from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_database_connection
from app.core.redis import check_redis_connection, get_arq_pool
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Verify health of API process, PostgreSQL, Redis, and ARQ queue."""
    db_ok = await check_database_connection()
    redis_ok = await check_redis_connection()

    worker_status = "ok"
    try:
        arq_pool = await get_arq_pool()
        # Verify arq connection can communicate with redis
        await arq_pool.ping()
    except Exception:
        worker_status = "degraded"

    services = {
        "database": "ok" if db_ok else "down",
        "redis": "ok" if redis_ok else "down",
        "worker_queue": worker_status,
    }

    all_healthy = db_ok and redis_ok
    overall_status = "ok" if all_healthy else "degraded"

    response_data = HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        services=services,
    )

    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=response_data.model_dump())
