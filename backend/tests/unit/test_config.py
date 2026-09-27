from app.core.config import Settings


def test_settings_cors_parsing():
    s = Settings(BACKEND_CORS_ORIGINS="http://localhost:3000, https://app.forgeai.dev")
    assert "http://localhost:3000" in s.BACKEND_CORS_ORIGINS
    assert "https://app.forgeai.dev" in s.BACKEND_CORS_ORIGINS


def test_settings_defaults():
    s = Settings()
    assert s.PROJECT_NAME == "Forge AI"
    assert s.API_V1_STR == "/api/v1"
    assert s.JWT_ALGORITHM == "HS256"


def test_production_security_validation_fails_on_defaults():
    import pytest

    # Default JWT secret in production must fail
    with pytest.raises(ValueError, match="JWT_SECRET must be set to a secure"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="super-secret-jwt-key-change-in-production-min-32-chars-forgeai",
        )

    # Insecure / short JWT secret
    with pytest.raises(ValueError, match="JWT_SECRET must be set to a secure"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="short-secret",
        )

    # Insecure encryption key
    with pytest.raises(ValueError, match="ENCRYPTION_KEY must be a valid 64-character"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="a" * 32,
            ENCRYPTION_KEY="invalid-length-key",
        )


def test_production_security_validation_passes_on_valid_keys():
    s = Settings(
        ENVIRONMENT="production",
        JWT_SECRET="valid-production-secret-min-32-chars-long!",
        ENCRYPTION_KEY="a" * 64,
        GITHUB_WEBHOOK_SECRET="secure-production-webhook-secret-xyz",
    )
    assert s.is_production is True

