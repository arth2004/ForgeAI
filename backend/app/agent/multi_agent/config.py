"""Multi-Agent Execution Configuration and Execution Guardrails for Phase 6."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MultiAgentExecutionGuards:
    """Deterministic cost, iteration, and timeout limits for Phase 6 runtime."""

    MAX_TOTAL_WORKFLOW_ITERATIONS: int = int(os.getenv("MAX_TOTAL_WORKFLOW_ITERATIONS", "15"))
    MAX_PLANNER_INVESTIGATION_STEPS: int = int(os.getenv("MAX_PLANNER_INVESTIGATION_STEPS", "5"))
    MAX_CODER_RETRY_CYCLES: int = int(os.getenv("MAX_CODER_RETRY_CYCLES", "3"))
    MAX_TEST_REPAIR_LOOPS: int = int(os.getenv("MAX_TEST_REPAIR_LOOPS", "3"))
    MAX_REVIEW_ITERATIONS: int = int(os.getenv("MAX_REVIEW_ITERATIONS", "2"))
    MAX_TOTAL_TOOL_CALLS: int = int(os.getenv("MAX_TOTAL_TOOL_CALLS", "30"))
    MAX_TOTAL_LLM_TOKENS: int = int(os.getenv("MAX_TOTAL_LLM_TOKENS", "150000"))
    MAX_WORKFLOW_TIMEOUT_SECONDS: int = int(os.getenv("MAX_WORKFLOW_TIMEOUT_SECONDS", "600"))

    # Rate limiting & retry policies (Configuration-driven, no silent unconfigured failover)
    ENABLE_429_BACKOFF_RETRY: bool = os.getenv("AGENT_ENABLE_429_BACKOFF", "true").lower() == "true"
    MAX_429_RETRIES: int = int(os.getenv("AGENT_MAX_429_RETRIES", "3"))
    INITIAL_BACKOFF_SECONDS: float = float(os.getenv("AGENT_INITIAL_BACKOFF_SECONDS", "1.0"))


@dataclass(frozen=True)
class RoleProviderConfig:
    """Configuration-driven model routing per specialized agent role."""

    planner_provider: str = os.getenv("AGENT_PLANNER_PROVIDER", os.getenv("AGENT_DEFAULT_PROVIDER", "gemini"))
    planner_model: str = os.getenv("AGENT_PLANNER_MODEL", os.getenv("AGENT_GEMINI_MODEL", "gemini-2.5-flash"))

    coder_provider: str = os.getenv("AGENT_CODER_PROVIDER", os.getenv("AGENT_DEFAULT_PROVIDER", "openai"))
    coder_model: str = os.getenv("AGENT_CODER_MODEL", os.getenv("AGENT_OPENAI_MODEL", "gpt-4o"))

    tester_provider: str = os.getenv("AGENT_TESTER_PROVIDER", os.getenv("AGENT_DEFAULT_PROVIDER", "groq"))
    tester_model: str = os.getenv("AGENT_TESTER_MODEL", os.getenv("AGENT_GROQ_MODEL", "llama-3.3-70b-versatile"))

    reviewer_provider: str = os.getenv("AGENT_REVIEWER_PROVIDER", os.getenv("AGENT_DEFAULT_PROVIDER", "gemini"))
    reviewer_model: str = os.getenv("AGENT_REVIEWER_MODEL", os.getenv("AGENT_GEMINI_MODEL", "gemini-2.5-pro"))


multi_agent_guards = MultiAgentExecutionGuards()
role_provider_config = RoleProviderConfig()
