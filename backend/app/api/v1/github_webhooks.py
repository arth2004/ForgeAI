"""GitHub Webhook Receiver Endpoint for Phase 7."""

import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.exceptions import UnauthorizedException
from app.schemas.github_pr import WebhookAcceptedResponse
from app.services.github.pr_ingestion_service import PRIngestionService
from app.services.github.pr_review_service import PRReviewService
from app.services.github.webhook_verifier import (
    validate_payload_size,
    verify_github_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _run_pr_review_background(task_id: uuid.UUID) -> None:
    """Asynchronous background worker to run PR review and SHA drift checks."""
    try:
        async with AsyncSessionLocal() as session:
            service = PRReviewService(session)
            await service.execute_review(task_id)
    except Exception as exc:
        logger.error("PR Review Background Task failed for task_id %s: %s", task_id, exc)


@router.post(
    "/webhooks",
    response_model=WebhookAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive and verify GitHub App webhook events",
)
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Authenticates GitHub HMAC-SHA256 signature, deduplicates delivery, and queues PR analysis."""
    # 1. Read raw body and validate payload size
    raw_body = await request.body()
    validate_payload_size(raw_body)

    # 2. Cryptographic HMAC-SHA256 Signature Verification
    if not x_hub_signature_256:
        raise UnauthorizedException("Missing X-Hub-Signature-256 header")

    if not verify_github_webhook_signature(raw_body, x_hub_signature_256):
        raise UnauthorizedException("Invalid X-Hub-Signature-256 signature")

    # 3. Delivery Header Check
    delivery_id = x_github_delivery or "unknown-delivery"
    event_type = x_github_event or "unknown-event"

    # 4. Parse JSON Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise UnauthorizedException(f"Malformed webhook JSON payload: {exc}") from exc

    action = payload.get("action")
    repo_id = payload.get("repository", {}).get("id")

    ingestion_service = PRIngestionService(db)

    # 5. Deduplication
    is_new = await ingestion_service.record_delivery(
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        repository_id=repo_id,
    )
    if not is_new:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "accepted",
                "delivery_id": delivery_id,
                "event": event_type,
                "action": action,
                "message": "Duplicate webhook delivery ignored.",
            },
        )

    # 6. Process Supported Events
    if event_type == "pull_request":
        res = await ingestion_service.ingest_pull_request_event(payload, delivery_id)
        if res:
            snapshot, review_task = res
            # Queue asynchronous analysis (in non-test environments)
            if settings.ENVIRONMENT != "test":
                background_tasks.add_task(_run_pr_review_background, review_task.id)



            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "accepted",
                    "delivery_id": delivery_id,
                    "event": event_type,
                    "action": action,
                    "task_id": str(review_task.id),
                    "snapshot_id": str(snapshot.id),
                },
            )

    # Acknowledge non-PR or unhandled actions with 202 Accepted
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "delivery_id": delivery_id,
            "event": event_type,
            "action": action,
            "message": "Event processed.",
        },
    )
