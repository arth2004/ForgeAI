import tempfile
from pathlib import Path

import pytest

from app.agent.patching.applier import PatchApplicationError, apply_patch_atomically
from app.agent.patching.diff_engine import generate_patch_unified_diff
from app.agent.patching.validator import (
    MAX_PATCH_FILES,
    PatchConflictError,
    PatchValidationError,
    compute_file_sha256,
    validate_patch_proposal,
)
from app.schemas.agent import (
    AffectedFile,
    ChangeType,
    ImplementationPlan,
    PatchFile,
    PatchHunk,
)


@pytest.fixture
def temp_workspace():
    """Creates a temporary workspace directory populated with base files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir)
        # Create sample files
        (ws_path / "app").mkdir(parents=True)
        auth_file = ws_path / "app" / "auth.py"
        auth_file.write_text("def authenticate():\n    return False\n", encoding="utf-8")

        config_file = ws_path / "config.py"
        config_file.write_text("DEBUG = True\nTIMEOUT = 30\n", encoding="utf-8")

        yield ws_path


def test_valid_patch_validation_and_diff(temp_workspace: Path):
    """Valid patch proposal passes validation and generates unified diff."""
    auth_path = temp_workspace / "app" / "auth.py"
    old_hash = compute_file_sha256(auth_path.read_bytes())

    patch = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        old_content_hash=old_hash,
        hunks=[
            PatchHunk(
                id="hunk-1",
                old_start=1,
                old_lines=2,
                new_start=1,
                new_lines=2,
                old_content="def authenticate():\n    return False\n",
                new_content="def authenticate():\n    return True\n",
            )
        ],
        reason="Enable authentication in auth.py",
    )

    validate_patch_proposal([patch], workspace_root=temp_workspace)
    diff_text, files_changed, added, removed = generate_patch_unified_diff([patch], temp_workspace)

    assert files_changed == 1
    assert "--- a/app/auth.py" in diff_text
    assert "+++ b/app/auth.py" in diff_text
    assert "+    return True" in diff_text
    assert "-    return False" in diff_text
    assert added > 0
    assert removed > 0


def test_path_traversal_rejection(temp_workspace: Path):
    """Rejects relative parent directory traversal."""
    patch = PatchFile(
        file_path="../../etc/passwd",
        operation="MODIFY",
        hunks=[PatchHunk(id="h1", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content="")],
    )
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([patch], workspace_root=temp_workspace)
    assert "Relative parent directory access" in str(exc.value)


def test_absolute_drive_path_rejection(temp_workspace: Path):
    """Rejects absolute Windows drive paths."""
    patch = PatchFile(
        file_path="C:/Windows/System32/drivers/etc/hosts",
        operation="MODIFY",
        hunks=[PatchHunk(id="h1", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content="")],
    )
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([patch], workspace_root=temp_workspace)
    assert "Absolute local filesystem drive paths are prohibited" in str(exc.value)


def test_null_byte_path_rejection(temp_workspace: Path):
    """Rejects null bytes in file paths."""
    patch = PatchFile(
        file_path="app/auth.py\x00.evil",
        operation="MODIFY",
        hunks=[PatchHunk(id="h1", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content="")],
    )
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([patch], workspace_root=temp_workspace)
    assert "prohibited null bytes" in str(exc.value)


def test_hash_mismatch_drift_protection(temp_workspace: Path):
    """Rejects patch with PATCH_CONFLICT when old_content_hash does not match workspace file."""
    patch = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        old_content_hash="0000000000000000000000000000000000000000000000000000000000000000",
        hunks=[PatchHunk(id="h1", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content="")],
    )
    with pytest.raises(PatchConflictError) as exc:
        validate_patch_proposal([patch], workspace_root=temp_workspace)
    assert "PATCH_CONFLICT" in str(exc.value)


def test_plan_grounding_rejection(temp_workspace: Path):
    """Rejects files not covered in the approved plan if no justification is given."""
    plan = ImplementationPlan(
        summary="Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[AffectedFile(file_path="app/auth.py", change_type=ChangeType.MODIFY, reason="Auth update")],
        test_strategy="Tests",
    )

    unrelated_patch = PatchFile(
        file_path="config.py",
        operation="MODIFY",
        old_content_hash=compute_file_sha256((temp_workspace / "config.py").read_bytes()),
        hunks=[PatchHunk(id="h1", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content="")],
        reason=None,  # No explicit justification
    )

    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([unrelated_patch], workspace_root=temp_workspace, approved_plan=plan)
    assert "not in approved plan and lacks explicit dependency justification" in str(exc.value)


def test_duplicate_hunk_id_rejection():
    """Rejects patches with duplicate hunk IDs."""
    patch = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        hunks=[
            PatchHunk(id="dup-hunk", old_start=1, old_lines=1, new_start=1, new_lines=1, old_content="", new_content=""),
            PatchHunk(id="dup-hunk", old_start=5, old_lines=1, new_start=5, new_lines=1, old_content="", new_content=""),
        ],
    )
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([patch], check_workspace_hashes=False)
    assert "Duplicate hunk id" in str(exc.value)


def test_overlapping_hunks_rejection():
    """Rejects patches with overlapping hunk line numbers."""
    patch = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        hunks=[
            PatchHunk(id="h1", old_start=1, old_lines=5, new_start=1, new_lines=5, old_content="", new_content=""),
            PatchHunk(id="h2", old_start=4, old_lines=3, new_start=4, new_lines=3, old_content="", new_content=""),
        ],
    )
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal([patch], check_workspace_hashes=False)
    assert "Overlapping or out-of-order hunk" in str(exc.value)


def test_excessive_files_limit():
    """Rejects patch exceeding MAX_PATCH_FILES limit."""
    files = [
        PatchFile(
            file_path=f"file_{i}.py",
            operation="CREATE",
            hunks=[PatchHunk(id=f"h{i}", old_start=1, old_lines=0, new_start=1, new_lines=1, old_content="", new_content="pass\n")],
        )
        for i in range(MAX_PATCH_FILES + 1)
    ]
    with pytest.raises(PatchValidationError) as exc:
        validate_patch_proposal(files, check_workspace_hashes=False)
    assert f"exceeds maximum limit of {MAX_PATCH_FILES}" in str(exc.value)


def test_atomic_patch_application_and_rollback(temp_workspace: Path):
    """Applies patch atomically and verifies post-application state and rollback on error."""
    auth_path = temp_workspace / "app" / "auth.py"
    old_auth_hash = compute_file_sha256(auth_path.read_bytes())


    # 1. Successful atomic application
    patch1 = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        old_content_hash=old_auth_hash,
        hunks=[
            PatchHunk(
                id="h1",
                old_start=1,
                old_lines=2,
                new_start=1,
                new_lines=2,
                old_content="def authenticate():\n    return False\n",
                new_content="def authenticate():\n    return True\n",
            )
        ],
    )
    patch2 = PatchFile(
        file_path="app/new_module.py",
        operation="CREATE",
        hunks=[
            PatchHunk(
                id="h2",
                old_start=1,
                old_lines=0,
                new_start=1,
                new_lines=1,
                old_content="",
                new_content="VERSION = 2\n",
            )
        ],
    )

    modified = apply_patch_atomically(temp_workspace, [patch1, patch2])
    assert len(modified) == 2
    assert "return True" in auth_path.read_text(encoding="utf-8")
    assert (temp_workspace / "app" / "new_module.py").exists()

    # 2. Failed patch with post-verification hash failure triggers rollback
    bad_patch = PatchFile(
        file_path="app/auth.py",
        operation="MODIFY",
        old_content_hash=compute_file_sha256(auth_path.read_bytes()),
        new_content_hash="mismatched_hash_value_that_will_fail_post_verification",
        hunks=[
            PatchHunk(
                id="h3",
                old_start=1,
                old_lines=2,
                new_start=1,
                new_lines=2,
                old_content="def authenticate():\n    return True\n",
                new_content="def authenticate():\n    return False\n",
            )
        ],
    )

    with pytest.raises(PatchApplicationError):
        apply_patch_atomically(temp_workspace, [bad_patch])

    # Verify rollback restored exact state
    assert "return True" in auth_path.read_text(encoding="utf-8")
