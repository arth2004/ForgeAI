import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.agent import (
    AgentTestExecution,
    AgentWorkspace,
    TestExecutionStatus,
    WorkspaceStatus,
)
from app.models.auth import Membership
from app.models.base import utc_now
from app.models.project import Project
from app.schemas.agent import (
    AgentTestExecutionRequest,
    AgentTestExecutionResponse,
    TestCommand,
)
from app.services.sandbox.runner import SandboxRunner

logger = logging.getLogger(__name__)


class TestExecutionService:
    """Service layer managing sandboxed test executions within ephemeral AgentWorkspaces."""

    def __init__(self, db: AsyncSession, sandbox_runner: SandboxRunner | None = None) -> None:
        self.db = db
        self.sandbox_runner = sandbox_runner or SandboxRunner()

    async def execute_test(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        request: AgentTestExecutionRequest,
    ) -> AgentTestExecutionResponse:
        """Executes a declarative test runner inside the isolated workspace sandbox."""
        # 1. Validate workspace
        workspace = await self.db.get(AgentWorkspace, workspace_id)
        if not workspace:
            raise NotFoundException("AgentWorkspace", workspace_id)
        if workspace.user_id != user_id:
            raise ForbiddenException("You do not have access to this workspace.")
        if workspace.status in (WorkspaceStatus.EXPIRED.value, WorkspaceStatus.DESTROYED.value, WorkspaceStatus.FAILED.value):
            raise ConflictException(f"Cannot execute tests on workspace in '{workspace.status}' state.")

        # 2. Authorize project
        project = await self.db.get(Project, workspace.project_id)
        if not project:
            raise NotFoundException("Project", workspace.project_id)

        membership_q = select(Membership).where(
            Membership.organization_id == project.organization_id,
            Membership.user_id == user_id,
        )
        mem_res = await self.db.execute(membership_q)
        if not mem_res.scalars().first():
            raise ForbiddenException("You do not have access to this project.")

        workspace_path = Path(workspace.path)
        session_id = request.session_id or workspace.session_id
        test_id = uuid.uuid4()
        started_at = utc_now()

        # 3. Create AgentTestExecution record in RUNNING status
        execution = AgentTestExecution(
            id=test_id,
            workspace_id=workspace_id,
            session_id=session_id,
            patch_id=request.patch_id,
            user_id=user_id,
            test_command=request.test_command.model_dump(),
            status=TestExecutionStatus.RUNNING.value,
            started_at=started_at,
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        logger.info(
            f"[test.started] test_id={test_id} workspace_id={workspace_id} "
            f"runner={request.test_command.runner} args={request.test_command.arguments}"
        )

        # 4. Run inside sandbox
        result = await self.sandbox_runner.run_test(
            workspace_path=workspace_path,
            test_command=request.test_command,
        )

        # 5. Record results
        completed_at = utc_now()
        execution.status = result.status.value
        execution.exit_code = result.exit_code
        execution.stdout = result.stdout
        execution.stderr = result.stderr
        execution.duration_ms = result.duration_ms
        execution.completed_at = completed_at

        await self.db.commit()
        await self.db.refresh(execution)

        logger.info(
            f"[test.completed] test_id={test_id} status={execution.status} exit_code={execution.exit_code} duration_ms={execution.duration_ms}"
        )

        return self._to_response(execution)

    async def get_test_execution(
        self,
        user_id: uuid.UUID,
        test_id: uuid.UUID,
    ) -> AgentTestExecutionResponse:
        """Retrieves an AgentTestExecution record ensuring authorization."""
        execution = await self.db.get(AgentTestExecution, test_id)
        if not execution:
            raise NotFoundException("AgentTestExecution", test_id)
        if execution.user_id != user_id:
            raise ForbiddenException("You do not have access to this test execution record.")

        return self._to_response(execution)

    def _to_response(self, execution: AgentTestExecution) -> AgentTestExecutionResponse:
        cmd = TestCommand.model_validate(execution.test_command)
        return AgentTestExecutionResponse(
            test_id=execution.id,
            workspace_id=execution.workspace_id,
            session_id=execution.session_id,
            patch_id=execution.patch_id,
            test_command=cmd,
            status=execution.status,
            exit_code=execution.exit_code,
            stdout=execution.stdout,
            stderr=execution.stderr,
            duration_ms=execution.duration_ms,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
        )
