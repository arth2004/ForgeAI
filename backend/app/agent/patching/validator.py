import hashlib
from pathlib import Path

from app.core.exceptions import ConflictException, ValidationException
from app.models.agent import PatchOperation
from app.schemas.agent import ImplementationPlan, PatchFile

MAX_PATCH_FILES = 20
MAX_HUNKS_PER_FILE = 100
MAX_TOTAL_PATCH_BYTES = 1024 * 1024  # 1 MB


class PatchValidationError(ValidationException):
    """Raised when a patch proposal fails structural or security validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message=f"Patch validation error: {message}")


class PatchConflictError(ConflictException):
    """Raised when workspace content drifted from old_content_hash (PATCH_CONFLICT)."""

    def __init__(self, file_path: str, expected_hash: str | None, actual_hash: str | None) -> None:
        super().__init__(
            message=f"PATCH_CONFLICT on file '{file_path}': expected hash '{expected_hash}', but workspace has '{actual_hash}'."
        )
        self.file_path = file_path
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


def compute_file_sha256(content: str | bytes) -> str:
    """Computes SHA256 hex digest for file content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def canonicalize_and_validate_path(file_path: str, workspace_root: Path | None = None) -> Path:
    """Validates that a file path is safe, relative, contains no traversals, and stays within workspace."""
    if not file_path or not file_path.strip():
        raise PatchValidationError("File path cannot be empty.")

    normalized = file_path.strip().replace("\\", "/")

    # Prohibit null bytes
    if "\x00" in normalized:
        raise PatchValidationError(f"File path contains prohibited null bytes: '{normalized}'.")

    # Prohibit absolute paths & drive letters
    if normalized.startswith("/") or normalized.startswith("\\"):
        raise PatchValidationError(f"Absolute filesystem paths are prohibited: '{file_path}'.")

    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        raise PatchValidationError(
            f"Absolute local filesystem drive paths are prohibited: '{file_path}'."
        )

    # Prohibit UNC paths
    if normalized.startswith("//") or normalized.startswith("\\\\"):
        raise PatchValidationError(f"UNC network paths are prohibited: '{file_path}'.")

    parts = [p for p in normalized.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise PatchValidationError(
            f"Relative parent directory access ('..') is prohibited: '{file_path}'."
        )

    clean_rel_path = Path(*parts)

    if workspace_root:
        canonical_workspace = workspace_root.resolve()
        target_path = (canonical_workspace / clean_rel_path).resolve()
        try:
            target_path.relative_to(canonical_workspace)
        except ValueError:
            raise PatchValidationError(
                f"Resolved path '{target_path}' escapes the workspace root '{canonical_workspace}'."
            ) from None

        # Check for symlink escapes
        if target_path.is_symlink():
            real_target = target_path.resolve()
            try:
                real_target.relative_to(canonical_workspace)
            except ValueError:
                raise PatchValidationError(
                    f"Symlink '{target_path}' resolves to target outside workspace '{real_target}'."
                ) from None

        return target_path

    return clean_rel_path


def validate_patch_proposal(
    files: list[PatchFile],
    workspace_root: Path | None = None,
    approved_plan: ImplementationPlan | None = None,
    check_workspace_hashes: bool = True,
) -> None:
    """Performs comprehensive server-side patch validation enforcing bounds, security, grounding, and hash drift."""
    if not files:
        raise PatchValidationError("Patch proposal must contain at least one file.")

    if len(files) > MAX_PATCH_FILES:
        raise PatchValidationError(
            f"Patch file count ({len(files)}) exceeds maximum limit of {MAX_PATCH_FILES} files."
        )

    total_bytes = 0
    seen_files: set[str] = set()
    valid_operations = {PatchOperation.CREATE.value, PatchOperation.MODIFY.value, PatchOperation.DELETE.value}

    # Extract allowed plan paths if plan is provided
    allowed_plan_paths: set[str] = set()
    if approved_plan:
        allowed_plan_paths.update(f.file_path.replace("\\", "/") for f in approved_plan.affected_files)
        allowed_plan_paths.update(p.replace("\\", "/") for p in approved_plan.new_files)
        allowed_plan_paths.update(p.replace("\\", "/") for p in approved_plan.deleted_files)

    for patch_file in files:
        clean_path_str = patch_file.file_path.strip().replace("\\", "/")
        if clean_path_str in seen_files:
            raise PatchValidationError(f"Duplicate file path in patch proposal: '{clean_path_str}'.")
        seen_files.add(clean_path_str)

        # 1. Path Safety & Canonicalization
        resolved_path = canonicalize_and_validate_path(clean_path_str, workspace_root)

        # 2. Operation Validation
        op_val = patch_file.operation.upper()
        if op_val not in valid_operations:
            raise PatchValidationError(
                f"Unsupported patch operation '{patch_file.operation}' for '{clean_path_str}'. "
                f"Must be one of: CREATE, MODIFY, DELETE."
            )

        # 3. Plan Grounding Check
        if approved_plan:
            is_in_plan = clean_path_str in allowed_plan_paths
            has_justification = bool(patch_file.reason and len(patch_file.reason.strip()) >= 5)
            if not is_in_plan and not has_justification:
                raise PatchValidationError(
                    f"File '{clean_path_str}' is not in approved plan and lacks explicit dependency justification."
                )

        # 4. Hunks Validation
        if len(patch_file.hunks) > MAX_HUNKS_PER_FILE:
            raise PatchValidationError(
                f"File '{clean_path_str}' contains {len(patch_file.hunks)} hunks, exceeding limit of {MAX_HUNKS_PER_FILE}."
            )

        seen_hunk_ids: set[str] = set()
        prev_end_line = 0

        for hunk in patch_file.hunks:
            if not hunk.id or not hunk.id.strip():
                raise PatchValidationError(f"Hunk missing required id in file '{clean_path_str}'.")
            if hunk.id in seen_hunk_ids:
                raise PatchValidationError(f"Duplicate hunk id '{hunk.id}' in file '{clean_path_str}'.")
            seen_hunk_ids.add(hunk.id)

            if hunk.old_start < 1 or hunk.new_start < 1:
                raise PatchValidationError(
                    f"Hunk '{hunk.id}' in '{clean_path_str}' has invalid start line (old: {hunk.old_start}, new: {hunk.new_start}). Line numbers must be >= 1."
                )

            if hunk.old_lines < 0 or hunk.new_lines < 0:
                raise PatchValidationError(
                    f"Hunk '{hunk.id}' in '{clean_path_str}' has negative line count."
                )

            # Check overlapping hunks for modifications
            if op_val == PatchOperation.MODIFY.value:
                if hunk.old_start <= prev_end_line:
                    raise PatchValidationError(
                        f"Overlapping or out-of-order hunk '{hunk.id}' in '{clean_path_str}' "
                        f"(starts at line {hunk.old_start}, previous hunk ended at {prev_end_line})."
                    )
                prev_end_line = hunk.old_start + max(0, hunk.old_lines - 1)

            hunk_bytes = len(hunk.old_content.encode("utf-8")) + len(hunk.new_content.encode("utf-8"))
            total_bytes += hunk_bytes

        # 5. Hash & Drift Protection (against live workspace if workspace_root provided)
        if workspace_root and check_workspace_hashes:
            if op_val == PatchOperation.CREATE.value:
                if resolved_path.exists():
                    actual_hash = compute_file_sha256(resolved_path.read_bytes())
                    raise PatchConflictError(clean_path_str, None, actual_hash)
            elif op_val in (PatchOperation.MODIFY.value, PatchOperation.DELETE.value):
                if not resolved_path.exists():
                    raise PatchConflictError(clean_path_str, patch_file.old_content_hash, None)

                actual_bytes = resolved_path.read_bytes()
                actual_hash = compute_file_sha256(actual_bytes)
                if patch_file.old_content_hash and actual_hash != patch_file.old_content_hash:
                    raise PatchConflictError(clean_path_str, patch_file.old_content_hash, actual_hash)

    # 6. Total Patch Size Limit
    if total_bytes > MAX_TOTAL_PATCH_BYTES:
        raise PatchValidationError(
            f"Total patch payload size ({total_bytes} bytes) exceeds maximum limit of {MAX_TOTAL_PATCH_BYTES} bytes (1MB)."
        )
