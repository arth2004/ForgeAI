import datetime
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    ForgeAIException,
    NotFoundException,
)
from app.models.agent import (
    AgentApproval,
    AgentSession,
    AgentWorkspace,
    ApprovalStatus,
    ApprovalType,
    WorkspaceStatus,
)
from app.models.auth import Membership
from app.models.base import utc_now
from app.models.codebase import IndexVersionStatus, RepositoryIndexVersion
from app.models.project import Project, RepositoryBranch
from app.schemas.agent import AgentWorkspaceResponse

logger = logging.getLogger(__name__)

WORKSPACE_TTL_MINUTES = 60


def get_workspace_base_root() -> Path:
    """Returns the dedicated root directory for ephemeral agent workspaces."""
    env_root = os.getenv("FORGE_WORKSPACE_ROOT")
    if env_root:
        root = Path(env_root)
    else:
        root = Path(tempfile.gettempdir()) / "forge_workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


class WorkspaceService:
    """Service layer managing isolated ephemeral workspaces, worktrees, and TTL lifecycles."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workspace(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> AgentWorkspaceResponse:
        """Provisions an isolated ephemeral AgentWorkspace after verified Plan approval."""
        # 1. Validate session
        session = await self.db.get(AgentSession, session_id)
        if not session:
            raise NotFoundException("AgentSession", session_id)

        if session.user_id != user_id:
            raise ForbiddenException("You do not have access to this agent session.")

        # 2. Authorize project
        project = await self.db.get(Project, session.project_id)
        if not project:
            raise NotFoundException("Project", session.project_id)

        membership_q = select(Membership).where(
            Membership.organization_id == project.organization_id,
            Membership.user_id == user_id,
        )
        membership_res = await self.db.execute(membership_q)
        if not membership_res.scalars().first():
            raise ForbiddenException("You do not have access to this project.")

        # 3. Validate approval
        approval = await self.db.get(AgentApproval, approval_id)
        if not approval:
            raise NotFoundException("AgentApproval", approval_id)

        if approval.user_id != user_id:
            raise ForbiddenException("You do not have permission to use this approval.")

        if approval.session_id != session_id:
            raise ConflictException(
                f"Approval {approval_id} is bound to session {approval.session_id}, not {session_id}."
            )

        if approval.approval_type != ApprovalType.PLAN.value:
            raise ConflictException(f"Approval type must be PLAN, got '{approval.approval_type}'.")

        if approval.status != ApprovalStatus.APPROVED.value:
            raise ConflictException(
                f"Approval {approval_id} is in '{approval.status}' state, not APPROVED."
            )

        # 4. Check concurrency / existing active workspace for session
        now = utc_now()
        existing_ws_q = select(AgentWorkspace).where(
            AgentWorkspace.session_id == session_id,
            AgentWorkspace.status.in_(
                [
                    WorkspaceStatus.CREATED.value,
                    WorkspaceStatus.PREPARED.value,
                    WorkspaceStatus.ACTIVE.value,
                ]
            ),
        )
        existing_ws_res = await self.db.execute(existing_ws_q)
        for existing_ws in existing_ws_res.scalars().all():
            if _ensure_utc(existing_ws.expires_at) > now:
                raise ConflictException(
                    f"An active workspace ({existing_ws.id}) already exists for session {session_id}."
                )

        # 5. Resolve base commit SHA
        base_sha = "0000000000000000000000000000000000000000"
        if session.repository_id:
            # Check active index version
            idx_q = (
                select(RepositoryIndexVersion)
                .where(
                    RepositoryIndexVersion.repository_id == session.repository_id,
                    RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
                )
                .order_by(RepositoryIndexVersion.created_at.desc())
            )
            idx_res = await self.db.execute(idx_q)
            active_idx = idx_res.scalars().first()
            if active_idx and active_idx.commit_sha:
                base_sha = active_idx.commit_sha
            elif session.branch_id:
                branch = await self.db.get(RepositoryBranch, session.branch_id)
                if branch and branch.latest_commit_sha:
                    base_sha = branch.latest_commit_sha

        # 6. Provision isolated workspace directory
        workspace_id = uuid.uuid4()
        ws_root = get_workspace_base_root()
        ws_path = ws_root / str(workspace_id)
        ws_path.mkdir(parents=True, exist_ok=True)

        expires_at = now + datetime.timedelta(minutes=WORKSPACE_TTL_MINUTES)

        # 7. Create and persist AgentWorkspace
        workspace = AgentWorkspace(
            id=workspace_id,
            session_id=session_id,
            organization_id=project.organization_id,
            project_id=session.project_id,
            repository_id=session.repository_id,
            branch_id=session.branch_id,
            user_id=user_id,
            status=WorkspaceStatus.PREPARED.value,
            path=str(ws_path),
            base_commit_sha=base_sha,
            expires_at=expires_at,
        )
        self.db.add(workspace)

        # Link approval to workspace
        approval.workspace_id = workspace_id

        await self.db.commit()
        await self.db.refresh(workspace)

        logger.info(
            f"[workspace.created] workspace_id={workspace.id} session_id={session_id} "
            f"user_id={user_id} base_sha={base_sha} expires_at={expires_at.isoformat()}"
        )

        return self._to_response(workspace)

    async def get_workspace(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> AgentWorkspaceResponse:
        """Retrieves an AgentWorkspace ensuring authorization and TTL enforcement."""
        workspace = await self.db.get(AgentWorkspace, workspace_id)
        if not workspace:
            raise NotFoundException("AgentWorkspace", workspace_id)

        if workspace.user_id != user_id:
            raise ForbiddenException("You do not have access to this workspace.")

        if repository_id is not None and workspace.repository_id != repository_id:
            raise ConflictException(
                f"Workspace {workspace_id} is bound to repository {workspace.repository_id}, not {repository_id}."
            )

        if branch_id is not None and workspace.branch_id is not None and workspace.branch_id != branch_id:
            raise ConflictException(
                f"Workspace {workspace_id} is bound to branch {workspace.branch_id}, not {branch_id}."
            )

        now = utc_now()
        if (
            _ensure_utc(workspace.expires_at) < now
            and workspace.status != WorkspaceStatus.DESTROYED.value
            and workspace.status != WorkspaceStatus.EXPIRED.value
        ):
            workspace.status = WorkspaceStatus.EXPIRED.value
            await self.db.commit()
            await self.db.refresh(workspace)
            raise ForgeAIException("Workspace has expired.", status_code=410)

        if workspace.status == WorkspaceStatus.EXPIRED.value:
            raise ForgeAIException("Workspace has expired.", status_code=410)

        return self._to_response(workspace)


    async def delete_workspace(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> AgentWorkspaceResponse:
        """Idempotently cleans up an ephemeral workspace and frees filesystem resources."""
        workspace = await self.db.get(AgentWorkspace, workspace_id)
        if not workspace:
            raise NotFoundException("AgentWorkspace", workspace_id)

        if workspace.user_id != user_id:
            raise ForbiddenException("You do not have permission to delete this workspace.")

        # Idempotent removal of workspace filesystem directory
        if workspace.path and os.path.exists(workspace.path):
            try:
                shutil.rmtree(workspace.path, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"[workspace.cleanup.warning] Failed to remove {workspace.path}: {exc}")

        workspace.status = WorkspaceStatus.DESTROYED.value
        workspace.destroyed_at = utc_now()

        await self.db.commit()
        await self.db.refresh(workspace)

        logger.info(f"[workspace.destroyed] workspace_id={workspace.id} user_id={user_id}")
        return self._to_response(workspace)

    @staticmethod
    def _to_response(workspace: AgentWorkspace) -> AgentWorkspaceResponse:
        return AgentWorkspaceResponse(
            workspace_id=workspace.id,
            session_id=workspace.session_id,
            organization_id=workspace.organization_id,
            project_id=workspace.project_id,
            repository_id=workspace.repository_id,
            branch_id=workspace.branch_id,
            user_id=workspace.user_id,
            status=workspace.status,
            path=workspace.path,
            base_commit_sha=workspace.base_commit_sha,
            created_at=workspace.created_at,
            expires_at=workspace.expires_at,
            destroyed_at=workspace.destroyed_at,
        )
