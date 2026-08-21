import logging
from pathlib import Path

from app.agent.patching.validator import (
    canonicalize_and_validate_path,
    compute_file_sha256,
    validate_patch_proposal,
)
from app.core.exceptions import ForgeAIException
from app.models.agent import PatchOperation
from app.schemas.agent import ImplementationPlan, PatchFile

logger = logging.getLogger(__name__)


class PatchApplicationError(ForgeAIException):
    """Raised when atomic patch application fails, triggering immediate rollback."""

    def __init__(self, message: str) -> None:
        super().__init__(message=f"Patch application failed (rolled back): {message}", status_code=500)


def apply_patch_atomically(
    workspace_root: Path,
    files: list[PatchFile],
    approved_plan: ImplementationPlan | None = None,
) -> list[str]:
    """Applies a list of PatchFiles atomically to workspace_root with pre-validation and rollback.

    Returns the list of modified file paths upon success.
    """
    canonical_ws = workspace_root.resolve()
    if not canonical_ws.exists() or not canonical_ws.is_dir():
        raise PatchApplicationError(f"Workspace directory '{canonical_ws}' does not exist.")

    # 1. Full pre-validation and hash checking
    validate_patch_proposal(
        files=files,
        workspace_root=canonical_ws,
        approved_plan=approved_plan,
        check_workspace_hashes=True,
    )

    # 2. Stage original state backup for rollback
    backup_state: dict[Path, bytes | None] = {}  # None indicates file did not exist before
    resolved_files: list[tuple[PatchFile, Path]] = []

    for patch_file in files:
        clean_path_str = patch_file.file_path.strip().replace("\\", "/")
        target_path = canonicalize_and_validate_path(clean_path_str, canonical_ws)
        resolved_files.append((patch_file, target_path))

        if target_path.exists():
            backup_state[target_path] = target_path.read_bytes()
        else:
            backup_state[target_path] = None

    modified_paths: list[str] = []

    try:
        # 3. Apply changes
        for patch_file, target_path in resolved_files:
            op_val = patch_file.operation.upper()
            clean_path_str = patch_file.file_path.strip().replace("\\", "/")

            if op_val == PatchOperation.CREATE.value:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                new_content = ""
                for hunk in patch_file.hunks:
                    if hunk.new_content:
                        new_content += hunk.new_content
                target_path.write_text(new_content, encoding="utf-8")
                modified_paths.append(clean_path_str)

            elif op_val == PatchOperation.MODIFY.value:
                original_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                new_doc: list[str] = []
                curr_line = 1

                for hunk in patch_file.hunks:
                    while curr_line < hunk.old_start and curr_line <= len(original_lines):
                        new_doc.append(original_lines[curr_line - 1])
                        curr_line += 1
                    if hunk.new_content:
                        new_doc.extend(hunk.new_content.splitlines(keepends=True))
                    curr_line += hunk.old_lines

                while curr_line <= len(original_lines):
                    new_doc.append(original_lines[curr_line - 1])
                    curr_line += 1

                target_path.write_text("".join(new_doc), encoding="utf-8")
                modified_paths.append(clean_path_str)

            elif op_val == PatchOperation.DELETE.value:
                if target_path.exists():
                    target_path.unlink()
                modified_paths.append(clean_path_str)

        # 4. Post-application verification: verify new_content_hash if specified
        for patch_file, target_path in resolved_files:
            op_val = patch_file.operation.upper()
            if op_val != PatchOperation.DELETE.value and patch_file.new_content_hash:
                if not target_path.exists():
                    raise PatchApplicationError(
                        f"Post-verification failed: file '{patch_file.file_path}' does not exist after application."
                    )
                actual_new_hash = compute_file_sha256(target_path.read_bytes())
                if actual_new_hash != patch_file.new_content_hash:
                    raise PatchApplicationError(
                        f"Post-verification hash mismatch on '{patch_file.file_path}': "
                        f"expected '{patch_file.new_content_hash}', got '{actual_new_hash}'."
                    )

        logger.info(
            f"[patch.applied] Successfully applied {len(files)} files to workspace '{canonical_ws}'"
        )
        return modified_paths

    except Exception as e:
        logger.error(f"[patch.rollback] Error during patch application: {e}. Initiating atomic rollback...")
        # Rollback all files
        for path, original_bytes in backup_state.items():
            try:
                if original_bytes is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original_bytes)
            except Exception as rollback_err:
                logger.critical(f"Failed to rollback file '{path}': {rollback_err}")

        if isinstance(e, PatchApplicationError):
            raise
        raise PatchApplicationError(str(e)) from e
