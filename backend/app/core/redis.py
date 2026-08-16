
import redis.asyncio as redis
from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import settings
from app.core.telemetry import logger

_redis_client: redis.Redis | None = None
_arq_pool: ArqRedis | None = None


def get_redis_settings() -> RedisSettings:
    """Parse Redis settings from REDIS_URL for ARQ."""
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def get_redis_client() -> redis.Redis:
    """Get or initialize singleton Redis async client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def get_arq_pool() -> ArqRedis:
    """Get or initialize singleton ARQ Redis pool for job enqueuing."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_redis_settings())
    return _arq_pool


async def check_redis_connection() -> bool:
    """Health check helper to verify Redis connectivity."""
    try:
        client = await get_redis_client()
        pong = await client.ping()
        return bool(pong)
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def close_redis():
    """Cleanup Redis connections on application shutdown."""
    global _redis_client, _arq_pool
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    if _arq_pool:
        await _arq_pool.close()
        _arq_pool = None
