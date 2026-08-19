import json
import re
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application Environment
    PROJECT_NAME: str = "Forge AI"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    # API Server
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    parsed = json.loads(v_str)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except Exception:
                    pass
            return [i.strip() for i in v_str.split(",") if i.strip()]
        elif isinstance(v, (list, set, tuple)):
            return [str(i).strip() for i in v if str(i).strip()]
        raise ValueError(f"Invalid CORS origin format: {v}")

    # PostgreSQL Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5433/forgeai"
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Any) -> str:
        if isinstance(v, str):
            # Guard against host OS environment variable contamination from unrelated projects
            if "expense_splitter" in v:
                v = "postgresql+asyncpg://postgres:postgres@localhost:5433/forgeai"
            if v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            if "schema=" in v:
                v = re.sub(r"[\?\&]schema=[^\&]+", "", v)
                if "?" not in v and "&" in v:
                    v = v.replace("&", "?", 1)
        return str(v)

    # Redis Cache & Broker
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Security & Cryptography
    JWT_SECRET: str = Field(
        default="super-secret-jwt-key-change-in-production-min-32-chars-forgeai"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)  # 24 hours

    # AES-256-GCM 32-byte key (64 hex characters or 32 bytes)
    ENCRYPTION_KEY: str = Field(
        default="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )

    # GitHub App Integration
    GITHUB_APP_ID: str = Field(default="")
    GITHUB_APP_SLUG: str = Field(default="forge-ai-app")
    GITHUB_CLIENT_ID: str = Field(default="")
    GITHUB_CLIENT_SECRET: str = Field(default="")
    GITHUB_PRIVATE_KEY: str = Field(default="")
    GITHUB_PRIVATE_KEY_PATH: str = Field(default="")
    GITHUB_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/github/callback")

    # Phase 3 Embedding & Indexing Settings
    EMBEDDING_PROVIDER: str = Field(default="google")
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_EMBEDDING_MODEL: str = Field(default="gemini-embedding-2")
    GEMINI_EMBEDDING_DIMENSION: int = Field(default=768)

    OPENAI_API_KEY: str = Field(default="")
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")
    OPENAI_EMBEDDING_DIMENSION: int = Field(default=768)

    # Ingestion & Repository Limits (Configurable)
    MAX_FILE_SIZE_BYTES: int = Field(default=1_048_576)  # 1 MB
    MAX_REPO_SIZE_BYTES: int = Field(default=524_288_000)  # 500 MB
    MAX_CHUNKS_PER_EMBED_BATCH: int = Field(default=100)
    INDEX_RETENTION_COUNT: int = Field(
        default=3, description="Number of SUPERSEDED index versions to retain per branch"
    )
    ARQ_JOB_TIMEOUT_SECONDS: int = Field(
        default=900, description="ARQ indexing worker job timeout in seconds (15 minutes)"
    )

    # Phase 4A Agent Foundation Settings
    AGENT_DEFAULT_PROVIDER: str = Field(default="google", description="Default LLM provider: google, openai, or mock")
    AGENT_GEMINI_MODEL: str = Field(default="gemini-2.5-pro", description="Default Google Gemini chat model")
    AGENT_OPENAI_MODEL: str = Field(default="gpt-4o", description="Default OpenAI chat model")
    AGENT_TEMPERATURE: float = Field(default=0.2, description="Default sampling temperature for agent reasoning")
    AGENT_MAX_TOKENS: int | None = Field(default=4096, description="Maximum token generation limit")
    AGENT_TIMEOUT_SECONDS: float = Field(default=60.0, description="Model invocation timeout in seconds")

    # Frontend URL
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()

