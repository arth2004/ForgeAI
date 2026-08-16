import logging
import sys

from app.core.config import settings


def setup_logging() -> logging.Logger:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Silence overly verbose third-party loggers if needed
    logging.getLogger("uvicorn.access").setLevel(log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("forgeai")
    logger.setLevel(log_level)
    return logger


logger = setup_logging()
