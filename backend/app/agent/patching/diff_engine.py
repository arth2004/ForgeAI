import difflib
from pathlib import Path

from app.agent.patching.validator import canonicalize_and_validate_path
from app.models.agent import PatchOperation
from app.schemas.agent import PatchFile


def generate_file_diff(
    patch_file: PatchFile,
    workspace_root: Path | None = None,
) -> tuple[str, int, int]:
    """Generates server-side unified diff string and (lines_added, lines_removed) stats for a single PatchFile."""
    file_path = patch_file.file_path.strip().replace("\\", "/")
    op_val = patch_file.operation.upper()

    original_lines: list[str] = []
    if workspace_root:
        full_path = canonicalize_and_validate_path(file_path, workspace_root)
        if full_path.exists() and op_val != PatchOperation.CREATE.value:
            try:
                original_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except Exception:
                original_lines = []

    # If no live workspace, reconstruct original from hunks
    if not original_lines and patch_file.hunks:
        # Build original from hunk old_content if MODIFY/DELETE
        if op_val in (PatchOperation.MODIFY.value, PatchOperation.DELETE.value):
            for hunk in patch_file.hunks:
                if hunk.old_content:
                    original_lines.extend(hunk.old_content.splitlines(keepends=True))

    target_lines: list[str] = []
    if op_val == PatchOperation.DELETE.value:
        target_lines = []
    elif op_val == PatchOperation.CREATE.value:
        for hunk in patch_file.hunks:
            if hunk.new_content:
                target_lines.extend(hunk.new_content.splitlines(keepends=True))
    else:  # MODIFY
        # Apply hunks to original lines
        if patch_file.hunks:
            new_doc: list[str] = []
            curr_line = 1
            for hunk in patch_file.hunks:
                # Add lines before hunk
                while curr_line < hunk.old_start and curr_line <= len(original_lines):
                    new_doc.append(original_lines[curr_line - 1])
                    curr_line += 1
                # Add new content lines
                if hunk.new_content:
                    new_doc.extend(hunk.new_content.splitlines(keepends=True))
                curr_line += hunk.old_lines
            # Add remaining lines
            while curr_line <= len(original_lines):
                new_doc.append(original_lines[curr_line - 1])
                curr_line += 1
            target_lines = new_doc
        else:
            target_lines = original_lines

    from_file = f"a/{file_path}" if op_val != PatchOperation.CREATE.value else "/dev/null"
    to_file = f"b/{file_path}" if op_val != PatchOperation.DELETE.value else "/dev/null"

    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            target_lines,
            fromfile=from_file,
            tofile=to_file,
            lineterm="\n",
        )
    )

    diff_text = "".join(diff_lines)
    lines_added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    lines_removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

    return diff_text, lines_added, lines_removed


def generate_patch_unified_diff(
    files: list[PatchFile],
    workspace_root: Path | None = None,
) -> tuple[str, int, int, int]:
    """Generates server-side unified diff for an entire Patch proposal with aggregate stats."""
    diff_chunks: list[str] = []
    total_added = 0
    total_removed = 0
    files_changed = len(files)

    for patch_file in files:
        f_diff, added, removed = generate_file_diff(patch_file, workspace_root)
        if f_diff:
            diff_chunks.append(f_diff)
        total_added += added
        total_removed += removed

    unified_diff = "\n".join(diff_chunks) if diff_chunks else ""
    return unified_diff, files_changed, total_added, total_removed
