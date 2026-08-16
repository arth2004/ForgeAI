import base64
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.exceptions import UnauthorizedException


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None
) -> str:
    """Create a signed JWT access token."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.now(UTC),
    }
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.PyJWTError as e:
        raise UnauthorizedException(f"Could not validate token: {str(e)}") from e


def _get_aes_gcm_key() -> bytes:
    """Derive 32-byte key from configured ENCRYPTION_KEY string."""
    raw = settings.ENCRYPTION_KEY
    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    # If base64 or raw string
    try:
        decoded = base64.b64decode(raw)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    # Pad or truncate to 32 bytes
    key_bytes = raw.encode("utf-8")
    if len(key_bytes) < 32:
        return key_bytes.ljust(32, b"0")
    return key_bytes[:32]


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string using AES-256-GCM. Returns base64 encoded nonce + ciphertext."""
    if not plaintext:
        return ""
    key = _get_aes_gcm_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_secret(encrypted_b64: str) -> str:
    """Decrypt a base64 encoded nonce + ciphertext using AES-256-GCM."""
    if not encrypted_b64:
        return ""
    try:
        raw = base64.b64decode(encrypted_b64.encode("utf-8"))
        nonce = raw[:12]
        ciphertext = raw[12:]
        key = _get_aes_gcm_key()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}") from e
