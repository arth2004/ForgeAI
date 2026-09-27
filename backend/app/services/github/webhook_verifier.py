"""GitHub Webhook Signature Verification and Security Layer."""

import hashlib
import hmac
import logging

from app.core.config import settings
from app.core.exceptions import UnauthorizedException

logger = logging.getLogger(__name__)


def verify_github_webhook_signature(
    raw_payload: bytes,
    signature_header: str | None,
    secret: str | None = None,
) -> bool:
    """Cryptographically verifies the HMAC-SHA256 signature of a GitHub webhook payload.

    Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
    Rejects missing, malformed, or invalid signatures.
    """
    if not signature_header:
        logger.warning("GitHub webhook rejected: missing X-Hub-Signature-256 header")
        return False

    webhook_secret = secret or settings.GITHUB_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("GitHub webhook verification failed: GITHUB_WEBHOOK_SECRET is not configured")
        return False

    if not signature_header.startswith("sha256="):
        logger.warning("GitHub webhook rejected: signature header missing 'sha256=' prefix")
        return False

    provided_signature = signature_header.removeprefix("sha256=").strip()

    # Compute HMAC-SHA256 digest
    computed_hmac = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    is_valid = hmac.compare_digest(computed_hmac, provided_signature)
    if not is_valid:
        logger.warning("GitHub webhook rejected: invalid HMAC-SHA256 signature")

    return is_valid


def validate_payload_size(raw_payload: bytes, max_bytes: int | None = None) -> None:
    """Enforces upper size limit on incoming webhook payloads to mitigate DoS attacks."""
    limit = max_bytes or settings.GITHUB_WEBHOOK_MAX_BYTES
    if len(raw_payload) > limit:
        raise UnauthorizedException(
            f"Webhook payload exceeds maximum allowable size ({len(raw_payload)} > {limit} bytes)"
        )
