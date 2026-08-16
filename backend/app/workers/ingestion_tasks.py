import logging
import uuid
from typing import Any

from app.services.ingestion.engine import IngestionEngine

logger = logging.getLogger(__name__)


async def index_repository_task(
    ctx: dict[str, Any],
    repository_id: str,
    branch_id: str,
    is_full_reindex: bool = False,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Background ARQ worker task to ingest, chunk, embed, and index a repository branch."""
    logger.info(
        f"Starting ARQ indexing task for repository {repository_id}, branch {branch_id} (full_reindex={is_full_reindex})"
    )

    repo_uuid = uuid.UUID(repository_id)
    branch_uuid = uuid.UUID(branch_id)
    job_uuid = uuid.UUID(job_id) if job_id else None

    version_id = await IngestionEngine.run_indexing(
        repository_id=repo_uuid,
        branch_id=branch_uuid,
        is_full_reindex=is_full_reindex,
        job_id=job_uuid,
    )

    return {
        "status": "completed",
        "repository_id": repository_id,
        "branch_id": branch_id,
        "index_version_id": str(version_id),
    }
