from typing import Any

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.telemetry import logger
from app.workers.health_tasks import health_check_job


async def startup(ctx: dict[str, Any]):
    logger.info("ARQ Worker starting up...")


async def shutdown(ctx: dict[str, Any]):
    logger.info("ARQ Worker shutting down...")


class WorkerSettings:
    """
    ARQ Worker configuration.
    Run via: python -m arq app.workers.main.WorkerSettings
    """
    functions = [health_check_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600  # Keep completed job results for 1 hour
