import pytest

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


def test_password_hashing():
    pwd = "superSecretPassword123!"
    hashed = hash_password(pwd)

    assert hashed != pwd
    assert hashed.startswith("$2b$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongPassword", hashed) is False


def test_jwt_token_flow():
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token(subject=user_id)

    assert isinstance(token, str)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_invalid_token():
    with pytest.raises(UnauthorizedException):
        decode_access_token("invalid.token.here")


def test_aes_256_gcm_encryption_decryption():
    secret_github_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    encrypted = encrypt_secret(secret_github_token)

    assert encrypted != secret_github_token
    assert isinstance(encrypted, str)

    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret_github_token


def test_aes_empty_string():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""
