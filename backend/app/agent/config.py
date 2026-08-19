from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class AgentConfig:
    """Immutable runtime configuration container for the Forge AI agent graph."""

    provider: str
    model_name: str
    temperature: float = 0.2
    max_tokens: int | None = 4096
    timeout_seconds: float = 60.0

    @classmethod
    def from_settings(
        cls,
        provider_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        timeout_override: float | None = None,
    ) -> "AgentConfig":
        """Factory creating AgentConfig using application settings with optional runtime overrides."""
        provider = (provider_override or settings.AGENT_DEFAULT_PROVIDER).lower()

        if model_override:
            model_name = model_override
        elif provider == "openai":
            model_name = settings.AGENT_OPENAI_MODEL
        elif provider == "mock":
            model_name = "mock-model"
        else:
            model_name = settings.AGENT_GEMINI_MODEL

        return cls(
            provider=provider,
            model_name=model_name,
            temperature=temperature_override
            if temperature_override is not None
            else settings.AGENT_TEMPERATURE,
            max_tokens=max_tokens_override
            if max_tokens_override is not None
            else settings.AGENT_MAX_TOKENS,
            timeout_seconds=timeout_override
            if timeout_override is not None
            else settings.AGENT_TIMEOUT_SECONDS,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes agent config to safe dictionary for logging or diagnostics."""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }
