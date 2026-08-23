"""Base Engineering Agent Protocol and common utilities for Phase 6."""

import abc
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.exceptions import AgentExecutionException
from app.agent.models import BaseChatModelProvider
from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.types import AgentRoleEnum

logger = logging.getLogger(__name__)


class BaseEngineeringAgent(abc.ABC):
    """Abstract base class for all specialized subagents in the multi-agent system."""

    def __init__(
        self,
        model_provider: BaseChatModelProvider,
        role: AgentRoleEnum,
        allowed_tools: set[str] | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.role = role
        self.allowed_tools = allowed_tools or set()

    def validate_tool_access(self, tool_name: str) -> None:
        """Enforces role-based tool execution boundaries to prevent privilege escalation."""
        if tool_name not in self.allowed_tools:
            logger.error(
                "Unauthorized tool invocation attempted: agent=%s tool=%s allowed=%s",
                self.role.value,
                tool_name,
                self.allowed_tools,
            )
            raise AgentExecutionException(
                f"Agent '{self.role.value}' is strictly forbidden from executing tool '{tool_name}'. "
                f"Allowed tools: {sorted(self.allowed_tools)}"
            )


    @abc.abstractmethod
    async def execute(
        self,
        state: MultiAgentState,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Executes one bounded step of the subagent, returning state delta updates."""
        raise NotImplementedError("Subclasses must implement execute()")
