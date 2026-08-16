import datetime
from typing import Any

from app.core.telemetry import logger


async def health_check_job(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """
    Test job executed by ARQ worker to verify the async queue processing pipeline:
    FastAPI -> Redis -> ARQ -> Worker -> Result.
    """
    timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    logger.info(f"ARQ Worker executing health_check_job with payload: {payload}")

    result = {
        "status": "success",
        "processed_at": timestamp,
        "input_payload": payload,
        "worker_name": "ForgeAI-ARQ-Worker",
    }
    return result
