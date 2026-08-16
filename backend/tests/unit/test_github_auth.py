import time
import uuid

import pytest

from app.core.exceptions import UnauthorizedException
from app.services.github.auth import GitHubAuthService


def test_generate_and_validate_state_success():
    user_id = uuid.uuid4()
    state = GitHubAuthService.generate_state(user_id)

    assert isinstance(state, str)
    assert len(state.split(":")) == 4

    validated_user_id = GitHubAuthService.validate_state(state)
    assert validated_user_id == user_id


def test_validate_state_tampered_signature_fails():
    user_id = uuid.uuid4()
    state = GitHubAuthService.generate_state(user_id)
    parts = state.split(":")

    # Alter the user ID in the payload while keeping the old signature
    tampered_state = f"{uuid.uuid4()}:{parts[1]}:{parts[2]}:{parts[3]}"

    with pytest.raises(UnauthorizedException, match="signature"):
        GitHubAuthService.validate_state(tampered_state)


def test_validate_state_expired_fails():
    user_id = uuid.uuid4()
    state = GitHubAuthService.generate_state(user_id)
    parts = state.split(":")

    # Pretend it was created 15 minutes ago (expiry is 10 minutes)
    expired_timestamp = int(time.time()) - 900
    expired_payload = f"{user_id}:{expired_timestamp}:{parts[2]}"

    import hashlib
    import hmac

    from app.core.config import settings

    signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        expired_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    expired_state = f"{expired_payload}:{signature}"

    with pytest.raises(UnauthorizedException, match="expired"):
        GitHubAuthService.validate_state(expired_state)


def test_validate_state_malformed_fails():
    with pytest.raises(UnauthorizedException, match="format"):
        GitHubAuthService.validate_state("not-a-valid-state")
