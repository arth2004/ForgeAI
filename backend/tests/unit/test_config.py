from app.core.config import Settings


def test_settings_cors_parsing():
    s = Settings(
        BACKEND_CORS_ORIGINS="http://localhost:3000, https://app.forgeai.dev"
    )
    assert "http://localhost:3000" in s.BACKEND_CORS_ORIGINS
    assert "https://app.forgeai.dev" in s.BACKEND_CORS_ORIGINS


def test_settings_defaults():
    s = Settings()
    assert s.PROJECT_NAME == "Forge AI"
    assert s.API_V1_STR == "/api/v1"
    assert s.JWT_ALGORITHM == "HS256"
