import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.services.git_service import GitService

logger = logging.getLogger(__name__)


class CreateBranchInput(BaseModel):
    """Schema for creating an isolated Git branch in a workspace."""

    workspace_id: uuid.UUID = Field(..., description="ID of the active AgentWorkspace.")
    branch_name: str | None = Field(
        default=None,
        description="Optional custom branch name (e.g. forge/issue-42-fix-auth). Defaults to forge/{session_id}.",
    )


class CreateBranchTool(BaseRepositoryTool):
    """Tool enabling the agent to create a local Git branch inside the isolated workspace."""

    @property
    def name(self) -> str:
        return "create_branch"

    @property
    def description(self) -> str:
        return (
            "Creates a local, isolated Git branch within the active ephemeral workspace. "
            "Branch names are strictly sanitized and protected branches (main, master, release) are rejected."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return CreateBranchInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        try:
            req = CreateBranchInput.model_validate(kwargs)
            service = GitService(db=db)
            res = await service.create_branch(
                user_id=user_id,
                workspace_id=req.workspace_id,
                branch_name=req.branch_name,
            )
            return ToolExecutionResult(
                tool_name=self.name,
                success=True,
                data={
                    "workspace_id": str(res.workspace_id),
                    "branch_name": res.branch_name,
                    "base_commit_sha": res.base_commit_sha,
                },
            )
        except Exception as e:
            logger.error(f"Error in create_branch tool: {e}")
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )


class GitStatusInput(BaseModel):
    """Schema for querying Git working tree status."""

    workspace_id: uuid.UUID = Field(..., description="ID of the active AgentWorkspace.")


class GitStatusTool(BaseRepositoryTool):
    """Tool enabling the agent to inspect the current Git working tree status of a workspace."""

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return (
            "Inspects the local Git working tree status inside the ephemeral workspace. "
            "Returns active branch, commit SHA, and lists of changed, staged, and untracked files."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return GitStatusInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        try:
            req = GitStatusInput.model_validate(kwargs)
            service = GitService(db=db)
            res = await service.get_git_status(
                user_id=user_id,
                workspace_id=req.workspace_id,
            )
            return ToolExecutionResult(
                tool_name=self.name,
                success=True,
                data={
                    "workspace_id": str(res.workspace_id),
                    "branch_name": res.branch_name,
                    "base_commit_sha": res.base_commit_sha,
                    "current_commit_sha": res.current_commit_sha,
                    "changed_files": res.changed_files,
                    "staged_files": res.staged_files,
                    "unstaged_files": res.unstaged_files,
                    "untracked_files": res.untracked_files,
                },
            )
        except Exception as e:
            logger.error(f"Error in git_status tool: {e}")
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )


class CommitChangesTool(BaseRepositoryTool):
    """Safety boundary tool: strictly forbids autonomous git commit by LLM tool calls."""

    @property
    def name(self) -> str:
        return "commit_changes"

    @property
    def description(self) -> str:
        return (
            "FORBIDDEN FOR AUTONOMOUS CALL: Commits require explicit authenticated human approval (Gate 3). "
            "Use POST /api/v1/agent/workspaces/{id}/commit after human approval is granted."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        class ForbiddenCommitInput(BaseModel):
            workspace_id: uuid.UUID = Field(..., description="ID of the workspace.")
            message: str | None = Field(default=None, description="Commit message.")

        return ForbiddenCommitInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        logger.warning(f"LLM attempted autonomous commit_changes call for user {user_id}. Blocked by security policy.")
        return ToolExecutionResult(
            tool_name=self.name,
            success=False,
            error=(
                "APPROVAL_REQUIRED: commit_changes cannot be executed autonomously by the agent. "
                "Committing requires explicit human approval via Gate 3 (POST /api/v1/agent/workspaces/{workspace_id}/commit)."
            ),
        )


class PushBranchTool(BaseRepositoryTool):
    """Safety boundary tool: strictly forbids autonomous git push by LLM tool calls."""

    @property
    def name(self) -> str:
        return "push_branch"

    @property
    def description(self) -> str:
        return (
            "FORBIDDEN FOR AUTONOMOUS CALL: Pushing to remote repositories requires explicit human approval (Gate 4). "
            "Use POST /api/v1/agent/workspaces/{id}/push after human approval is granted."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        class ForbiddenPushInput(BaseModel):
            workspace_id: uuid.UUID = Field(..., description="ID of the workspace.")

        return ForbiddenPushInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        logger.warning(f"LLM attempted autonomous push_branch call for user {user_id}. Blocked by security policy.")
        return ToolExecutionResult(
            tool_name=self.name,
            success=False,
            error=(
                "APPROVAL_REQUIRED: push_branch cannot be executed autonomously by the agent. "
                "Pushing to remote repositories requires explicit human approval via Gate 4 (POST /api/v1/agent/workspaces/{workspace_id}/push)."
            ),
        )


class CreatePullRequestTool(BaseRepositoryTool):
    """Safety boundary tool: strictly forbids autonomous PR creation by LLM tool calls."""

    @property
    def name(self) -> str:
        return "create_pull_request"

    @property
    def description(self) -> str:
        return (
            "FORBIDDEN FOR AUTONOMOUS CALL: Creating GitHub Pull Requests requires explicit human approval (Gate 5). "
            "Use POST /api/v1/agent/pulls/{id}/create after human approval is granted."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        class ForbiddenPRInput(BaseModel):
            workspace_id: uuid.UUID = Field(..., description="ID of the workspace.")

        return ForbiddenPRInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        logger.warning(f"LLM attempted autonomous create_pull_request call for user {user_id}. Blocked by security policy.")
        return ToolExecutionResult(
            tool_name=self.name,
            success=False,
            error=(
                "APPROVAL_REQUIRED: create_pull_request cannot be executed autonomously by the agent. "
                "Creating a GitHub Pull Request requires explicit human approval via Gate 5 (POST /api/v1/agent/pulls/{id}/create)."
            ),
        )
