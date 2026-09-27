"""Unit tests for GitHub Webhook HMAC-SHA256 signature verification and security limits."""

import hashlib
import hmac

import pytest

from app.core.exceptions import UnauthorizedException
from app.services.github.webhook_verifier import (
    validate_payload_size,
    verify_github_webhook_signature,
)


def _generate_signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_webhook_signature():
    secret = "test-webhook-secret-12345"
    payload = b'{"action":"opened","number":42}'
    sig = _generate_signature(payload, secret)

    assert verify_github_webhook_signature(payload, sig, secret=secret) is True


def test_invalid_webhook_signature():
    secret = "test-webhook-secret-12345"
    payload = b'{"action":"opened","number":42}'
    bad_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    assert verify_github_webhook_signature(payload, bad_sig, secret=secret) is False


def test_missing_webhook_signature():
    secret = "test-webhook-secret-12345"
    payload = b'{"action":"opened","number":42}'

    assert verify_github_webhook_signature(payload, None, secret=secret) is False
    assert verify_github_webhook_signature(payload, "", secret=secret) is False


def test_malformed_signature_prefix():
    secret = "test-webhook-secret-12345"
    payload = b'{"action":"opened","number":42}'
    raw_digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # Missing "sha256=" prefix
    assert verify_github_webhook_signature(payload, raw_digest, secret=secret) is False
    # Wrong prefix
    assert verify_github_webhook_signature(payload, f"sha1={raw_digest}", secret=secret) is False


def test_tampered_payload_rejected():
    secret = "test-webhook-secret-12345"
    original_payload = b'{"action":"opened","number":42}'
    tampered_payload = b'{"action":"opened","number":43}'
    sig = _generate_signature(original_payload, secret)

    assert verify_github_webhook_signature(tampered_payload, sig, secret=secret) is False


def test_payload_size_validation():
    small_payload = b"a" * 1024
    validate_payload_size(small_payload, max_bytes=2048)  # Should not raise

    large_payload = b"a" * 5000
    with pytest.raises(UnauthorizedException) as exc:
        validate_payload_size(large_payload, max_bytes=2048)
    assert "exceeds maximum allowable size" in str(exc.value)
