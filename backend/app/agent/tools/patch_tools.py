import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.base import BaseRepositoryTool, ToolExecutionResult
from app.schemas.agent import (
    AgentPatchProposalRequest,
    AgentTestExecutionRequest,
    PatchFile,
    TestCommand,
)

logger = logging.getLogger(__name__)


class ProposePatchInput(BaseModel):
    """Schema for proposing a structured patch proposal."""

    workspace_id: uuid.UUID = Field(..., description="ID of the active ephemeral AgentWorkspace.")
    session_id: uuid.UUID = Field(..., description="ID of the current AgentSession.")
    summary: str = Field(..., description="High-level summary of the patch.")
    files: list[PatchFile] = Field(..., description="List of structured patch files.")
    associated_plan_id: uuid.UUID | None = Field(
        default=None, description="Optional ID of approved ImplementationPlan."
    )


class ProposePatchTool(BaseRepositoryTool):
    """Tool enabling the agent to propose a structured patch for validation and human diff review."""

    @property
    def name(self) -> str:
        return "propose_patch"

    @property
    def description(self) -> str:
        return (
            "Proposes a structured, atomic patch to modify, create, or delete repository files in an ephemeral workspace. "
            "The proposal is strictly validated server-side and presented to the human user for DIFF approval."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return ProposePatchInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        try:
            from app.services.patch_service import PatchService

            req = ProposePatchInput.model_validate(kwargs)
            service = PatchService(db=db)
            res = await service.propose_patch(
                user_id=user_id,
                request=AgentPatchProposalRequest(
                    workspace_id=req.workspace_id,

                    session_id=req.session_id,
                    summary=req.summary,
                    files=req.files,
                    associated_plan_id=req.associated_plan_id,
                ),
            )
            return ToolExecutionResult(
                tool_name=self.name,
                success=True,
                data={
                    "patch_id": str(res.patch_id),
                    "status": res.status,
                    "summary": res.summary,
                    "files_count": len(res.files),
                    "approval_id": str(res.approval_id) if res.approval_id else None,
                    "message": "Patch proposal submitted and validated. Awaiting Human DIFF approval.",
                },
            )
        except Exception as e:
            logger.error(f"Error in propose_patch tool: {e}")
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )


class RunTestsInput(BaseModel):
    """Schema for executing a sandboxed test runner."""

    workspace_id: uuid.UUID = Field(..., description="ID of the active AgentWorkspace.")
    runner: str = Field(..., description="Allowlisted runner: pytest, ruff, npm_test, npm_build, cargo_test.")
    arguments: list[str] = Field(
        default_factory=list, description="Allowlisted arguments with no shell operators."
    )
    working_directory: str | None = Field(
        default=None, description="Optional relative subdirectory in workspace."
    )
    timeout_seconds: int = Field(default=120, description="Timeout in seconds (max 300).")


class RunTestsTool(BaseRepositoryTool):
    """Tool enabling the agent to execute allowlisted declarative test runners in an isolated sandbox."""

    @property
    def name(self) -> str:
        return "run_tests"

    @property
    def description(self) -> str:
        return (
            "Executes allowlisted test suites and linters (pytest, ruff, npm_test, cargo_test) inside an isolated "
            "container sandbox with no network access. Returns structured test exit codes, duration, and output logs."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return RunTestsInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        try:
            from app.services.test_execution_service import TestExecutionService

            req = RunTestsInput.model_validate(kwargs)
            service = TestExecutionService(db=db)
            cmd = TestCommand(
                runner=req.runner,
                arguments=req.arguments,
                working_directory=req.working_directory,
                timeout_seconds=req.timeout_seconds,
            )

            res = await service.execute_test(
                user_id=user_id,
                workspace_id=req.workspace_id,
                request=AgentTestExecutionRequest(test_command=cmd),
            )
            return ToolExecutionResult(
                tool_name=self.name,
                success=(res.exit_code == 0) if res.exit_code is not None else False,
                data={
                    "test_id": str(res.test_id),
                    "status": res.status,
                    "exit_code": res.exit_code,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "duration_ms": res.duration_ms,
                },
            )
        except Exception as e:
            logger.error(f"Error in run_tests tool: {e}")
            return ToolExecutionResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )


class ApplyPatchTool(BaseRepositoryTool):
    """Safety boundary tool: explicitly forbids autonomous patch application by the LLM."""

    @property
    def name(self) -> str:
        return "apply_patch"

    @property
    def description(self) -> str:
        return (
            "FORBIDDEN FOR AUTONOMOUS AGENT CALL: Patches can NEVER be applied directly by tool invocation. "
            "Patches require an explicit authenticated human API approval action via Gate 2."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        class ForbiddenApplyInput(BaseModel):
            patch_id: uuid.UUID = Field(..., description="ID of the patch.")

        return ForbiddenApplyInput

    async def aexecute(
        self, db: AsyncSession, user_id: uuid.UUID, **kwargs: Any
    ) -> ToolExecutionResult:
        logger.warning(f"LLM attempted autonomous apply_patch call for user {user_id}. Blocked by security policy.")
        return ToolExecutionResult(
            tool_name=self.name,
            success=False,
            error=(
                "APPROVAL_REQUIRED: apply_patch cannot be called autonomously by the agent. "
                "Patch application is strictly human-gated and requires explicit authenticated approval "
                "via POST /api/v1/agent/patches/{patch_id}/apply."
            ),
        )
