import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.patching.applier import apply_patch_atomically
from app.agent.patching.diff_engine import generate_patch_unified_diff
from app.agent.patching.validator import validate_patch_proposal
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.agent import (
    AgentApproval,
    AgentPatch,
    AgentSession,
    AgentWorkspace,
    ApprovalStatus,
    ApprovalType,
    PatchStatus,
    WorkspaceStatus,
)
from app.models.auth import Membership
from app.models.base import utc_now
from app.models.project import Project
from app.schemas.agent import (
    AgentPatchApplyResponse,
    AgentPatchProposalRequest,
    AgentPatchResponse,
    ImplementationPlan,
    PatchDiffResponse,
    PatchFile,
)

logger = logging.getLogger(__name__)


class PatchService:
    """Service layer managing structured AgentPatch proposals, server-side diffs, approval gates, and atomic application."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def propose_patch(
        self,
        user_id: uuid.UUID,
        request: AgentPatchProposalRequest,
    ) -> AgentPatchResponse:
        """Validates a structured patch proposal, generates server-side diff, and creates a pending DIFF approval gate."""
        # 1. Validate session & workspace
        session = await self.db.get(AgentSession, request.session_id)
        if not session:
            raise NotFoundException("AgentSession", request.session_id)
        if session.user_id != user_id:
            raise ForbiddenException("You do not have access to this agent session.")

        workspace = await self.db.get(AgentWorkspace, request.workspace_id)
        if not workspace:
            raise NotFoundException("AgentWorkspace", request.workspace_id)
        if workspace.user_id != user_id:
            raise ForbiddenException("You do not have access to this workspace.")
        if workspace.session_id != request.session_id:
            raise ConflictException(
                f"Workspace {workspace.id} is bound to session {workspace.session_id}, not {request.session_id}."
            )
        if workspace.status in (WorkspaceStatus.EXPIRED.value, WorkspaceStatus.DESTROYED.value, WorkspaceStatus.FAILED.value):
            raise ConflictException(f"Cannot propose patch on workspace in '{workspace.status}' state.")

        # 2. Authorize project
        project = await self.db.get(Project, session.project_id)
        if not project:
            raise NotFoundException("Project", session.project_id)

        membership_q = select(Membership).where(
            Membership.organization_id == project.organization_id,
            Membership.user_id == user_id,
        )
        mem_res = await self.db.execute(membership_q)
        if not mem_res.scalars().first():
            raise ForbiddenException("You do not have access to this project.")

        # 3. Retrieve approved plan if associated_plan_id provided or latest approved plan in session
        approved_plan: ImplementationPlan | None = None
        plan_approval_q = (
            select(AgentApproval)
            .where(
                AgentApproval.session_id == request.session_id,
                AgentApproval.approval_type == ApprovalType.PLAN.value,
                AgentApproval.status == ApprovalStatus.APPROVED.value,
            )
            .order_by(AgentApproval.created_at.desc())
        )
        plan_appr_res = await self.db.execute(plan_approval_q)
        plan_appr = plan_appr_res.scalars().first()
        if plan_appr and plan_appr.plan_payload:
            try:
                approved_plan = ImplementationPlan.model_validate(plan_appr.plan_payload)
            except Exception:
                approved_plan = None

        workspace_path = Path(workspace.path)

        # 4. Perform strict server-side validation & hash checking
        validate_patch_proposal(
            files=request.files,
            workspace_root=workspace_path,
            approved_plan=approved_plan,
            check_workspace_hashes=True,
        )

        # 5. Generate server-side unified diff
        diff_content, files_changed, lines_added, lines_removed = generate_patch_unified_diff(
            files=request.files,
            workspace_root=workspace_path,
        )

        patch_id = uuid.uuid4()

        # 6. Create AgentPatch record in AWAITING_APPROVAL status
        patch = AgentPatch(
            id=patch_id,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            user_id=user_id,
            status=PatchStatus.AWAITING_APPROVAL.value,
            summary=request.summary,
            files=[f.model_dump() for f in request.files],
            diff_content=diff_content,
        )
        self.db.add(patch)
        await self.db.flush()

        # 7. Create DIFF human approval gate in PENDING status
        approval = AgentApproval(
            id=uuid.uuid4(),
            session_id=request.session_id,
            workspace_id=request.workspace_id,
            patch_id=patch_id,
            user_id=user_id,
            approval_type=ApprovalType.DIFF.value,
            status=ApprovalStatus.PENDING.value,
            plan_payload={"summary": request.summary, "files_changed": files_changed},
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(patch)

        logger.info(
            f"[patch.proposed] patch_id={patch.id} workspace_id={workspace.id} "
            f"user_id={user_id} files={len(request.files)} approval_id={approval.id}"
        )

        return self._to_patch_response(patch, approval_id=approval.id)

    async def get_patch(self, user_id: uuid.UUID, patch_id: uuid.UUID) -> AgentPatchResponse:
        """Retrieves an AgentPatch proposal record ensuring authorization."""
        patch = await self.db.get(AgentPatch, patch_id)
        if not patch:
            raise NotFoundException("AgentPatch", patch_id)
        if patch.user_id != user_id:
            raise ForbiddenException("You do not have access to this patch.")

        # Find associated approval
        appr_q = select(AgentApproval).where(
            AgentApproval.patch_id == patch_id,
            AgentApproval.approval_type == ApprovalType.DIFF.value,
        )
        appr_res = await self.db.execute(appr_q)
        appr = appr_res.scalars().first()
        approval_id = appr.id if appr else None

        return self._to_patch_response(patch, approval_id=approval_id)

    async def get_patch_diff(self, user_id: uuid.UUID, patch_id: uuid.UUID) -> PatchDiffResponse:
        """Retrieves the unified diff representation of a patch."""
        patch = await self.db.get(AgentPatch, patch_id)
        if not patch:
            raise NotFoundException("AgentPatch", patch_id)
        if patch.user_id != user_id:
            raise ForbiddenException("You do not have access to this patch.")

        files = [PatchFile.model_validate(f) for f in patch.files]
        workspace = await self.db.get(AgentWorkspace, patch.workspace_id)
        ws_path = Path(workspace.path) if workspace else None

        if patch.diff_content:
            diff_text = patch.diff_content
            lines = diff_text.splitlines()
            added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
            removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
            files_changed = len(files)
        else:
            diff_text, files_changed, added, removed = generate_patch_unified_diff(files, ws_path)


        return PatchDiffResponse(
            patch_id=patch.id,
            workspace_id=patch.workspace_id,
            unified_diff=diff_text,
            files_changed=files_changed,
            lines_added=added,
            lines_removed=removed,
        )

    async def approve_patch(
        self,
        user_id: uuid.UUID,
        patch_id: uuid.UUID,
        reason: str | None = None,
    ) -> AgentPatchResponse:
        """Human approval action transitioning DIFF gate to APPROVED."""
        patch = await self.db.get(AgentPatch, patch_id)
        if not patch:
            raise NotFoundException("AgentPatch", patch_id)
        if patch.user_id != user_id:
            raise ForbiddenException("You do not have permission to approve this patch.")

        if patch.status == PatchStatus.APPLIED.value:
            raise ConflictException("Patch has already been applied.")

        appr_q = select(AgentApproval).where(
            AgentApproval.patch_id == patch_id,
            AgentApproval.approval_type == ApprovalType.DIFF.value,
        )
        appr_res = await self.db.execute(appr_q)
        appr = appr_res.scalars().first()
        if not appr:
            raise NotFoundException("AgentApproval", f"for patch {patch_id}")

        if appr.status == ApprovalStatus.APPROVED.value:
            raise ConflictException("Patch approval is already in APPROVED state.")
        if appr.status == ApprovalStatus.REJECTED.value:
            raise ConflictException("Cannot approve a previously REJECTED patch.")

        appr.status = ApprovalStatus.APPROVED.value
        appr.resolved_at = utc_now()
        patch.status = PatchStatus.APPROVED.value

        await self.db.commit()
        await self.db.refresh(patch)
        await self.db.refresh(appr)

        logger.info(f"[patch.approved] patch_id={patch.id} user_id={user_id}")
        return self._to_patch_response(patch, approval_id=appr.id)

    async def reject_patch(
        self,
        user_id: uuid.UUID,
        patch_id: uuid.UUID,
        reason: str | None = None,
    ) -> AgentPatchResponse:
        """Human rejection action transitioning DIFF gate to REJECTED."""
        patch = await self.db.get(AgentPatch, patch_id)
        if not patch:
            raise NotFoundException("AgentPatch", patch_id)
        if patch.user_id != user_id:
            raise ForbiddenException("You do not have permission to reject this patch.")

        if patch.status == PatchStatus.APPLIED.value:
            raise ConflictException("Cannot reject a patch that has already been applied.")

        appr_q = select(AgentApproval).where(
            AgentApproval.patch_id == patch_id,
            AgentApproval.approval_type == ApprovalType.DIFF.value,
        )
        appr_res = await self.db.execute(appr_q)
        appr = appr_res.scalars().first()
        if not appr:
            raise NotFoundException("AgentApproval", f"for patch {patch_id}")

        appr.status = ApprovalStatus.REJECTED.value
        appr.rejection_reason = reason
        appr.resolved_at = utc_now()
        patch.status = PatchStatus.REJECTED.value

        await self.db.commit()
        await self.db.refresh(patch)
        await self.db.refresh(appr)

        logger.info(f"[patch.rejected] patch_id={patch.id} user_id={user_id} reason={reason}")
        return self._to_patch_response(patch, approval_id=appr.id)

    async def apply_patch(
        self,
        user_id: uuid.UUID,
        patch_id: uuid.UUID,
    ) -> AgentPatchApplyResponse:
        """Authoritative patch application gate: verifies explicit human approval, applies changes atomically, and updates workspace state."""
        patch = await self.db.get(AgentPatch, patch_id)
        if not patch:
            raise NotFoundException("AgentPatch", patch_id)
        if patch.user_id != user_id:
            raise ForbiddenException("You do not have permission to apply this patch.")

        if patch.status == PatchStatus.APPLIED.value:
            raise ConflictException("This patch has already been applied.")

        # 1. Authoritative Approval Gate Verification
        appr_q = select(AgentApproval).where(
            AgentApproval.patch_id == patch_id,
            AgentApproval.approval_type == ApprovalType.DIFF.value,
        )
        appr_res = await self.db.execute(appr_q)
        approval = appr_res.scalars().first()

        if not approval:
            raise ForbiddenException("No human approval record exists for this patch.")
        if approval.user_id != user_id:
            raise ForbiddenException("Approval record belongs to a different user.")
        if approval.status != ApprovalStatus.APPROVED.value:
            raise ConflictException(
                f"Patch cannot be applied: approval gate is in '{approval.status}' state (requires APPROVED)."
            )

        workspace = await self.db.get(AgentWorkspace, patch.workspace_id)
        if not workspace:
            raise NotFoundException("AgentWorkspace", patch.workspace_id)
        if workspace.status in (WorkspaceStatus.EXPIRED.value, WorkspaceStatus.DESTROYED.value, WorkspaceStatus.FAILED.value):
            raise ConflictException(f"Cannot apply patch to workspace in '{workspace.status}' state.")

        workspace_path = Path(workspace.path)
        files = [PatchFile.model_validate(f) for f in patch.files]

        # 2. Atomic Application with Pre-validation and Rollback
        modified_paths = apply_patch_atomically(
            workspace_root=workspace_path,
            files=files,
        )

        now = utc_now()
        patch.status = PatchStatus.APPLIED.value
        patch.applied_at = now
        workspace.status = WorkspaceStatus.ACTIVE.value

        await self.db.commit()
        await self.db.refresh(patch)
        await self.db.refresh(workspace)

        logger.info(
            f"[patch.applied] patch_id={patch.id} workspace_id={workspace.id} files_modified={len(modified_paths)}"
        )

        return AgentPatchApplyResponse(
            patch_id=patch.id,
            workspace_id=workspace.id,
            status=patch.status,
            applied_at=now,
            files_modified=modified_paths,
        )

    def _to_patch_response(self, patch: AgentPatch, approval_id: uuid.UUID | None = None) -> AgentPatchResponse:
        files = [PatchFile.model_validate(f) for f in patch.files]
        return AgentPatchResponse(
            patch_id=patch.id,
            workspace_id=patch.workspace_id,
            session_id=patch.session_id,
            status=patch.status,
            summary=patch.summary,
            files=files,
            diff_content=patch.diff_content,
            approval_id=approval_id,
            created_at=patch.created_at,
            applied_at=patch.applied_at,
        )
