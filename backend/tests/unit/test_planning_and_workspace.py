
import pytest

from app.agent.planning.validator import (
    MAX_PLAN_FIELD_LENGTH,
    MAX_PLAN_FILES,
    PlanValidationError,
    validate_implementation_plan,
)
from app.schemas.agent import (
    AffectedFile,
    AgentSourceReference,
    ChangeType,
    ImplementationPlan,
)


def test_valid_implementation_plan():
    """Valid plan passes schema and structure validation."""
    plan = ImplementationPlan(
        summary="Refactor token parsing",
        problem_statement="Token validation does not handle edge cases.",
        approach="Update token decoding in service layer.",
        affected_files=[
            AffectedFile(
                file_path="app/auth/service.py",
                change_type=ChangeType.MODIFY,
                reason="Update token decode logic.",
                symbols=["decode_token"],
            )
        ],
        new_files=[],
        deleted_files=[],
        symbols=["decode_token"],
        test_strategy="Run unit tests in test_auth.py.",
        risks=["Ensure backward compatibility with older tokens."],
    )

    validated = validate_implementation_plan(plan)
    assert validated.summary == "Refactor token parsing"
    assert len(validated.affected_files) == 1
    assert validated.affected_files[0].change_type == ChangeType.MODIFY


def test_plan_validation_path_traversal_rejection():
    """Rejects path traversal attempts in affected_files."""
    plan = ImplementationPlan(
        summary="Malicious Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="../../etc/passwd",
                change_type=ChangeType.MODIFY,
                reason="Overwrite passwd",
            )
        ],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "Relative parent directory access" in str(exc.value)


def test_plan_validation_absolute_drive_path_rejection():
    """Rejects absolute Windows drive letters in file paths."""
    plan = ImplementationPlan(
        summary="Absolute Path Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="C:/Windows/System32/drivers/etc/hosts",
                change_type=ChangeType.MODIFY,
                reason="Modify hosts file",
            )
        ],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "Absolute local filesystem drive paths are prohibited" in str(exc.value)


def test_plan_validation_null_byte_rejection():
    """Rejects null bytes in file paths."""
    plan = ImplementationPlan(
        summary="Null Byte Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="app/auth/service.py\x00.evil",
                change_type=ChangeType.MODIFY,
                reason="Null byte attack",
            )
        ],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "null bytes" in str(exc.value).lower()


def test_plan_validation_duplicate_files_rejection():
    """Rejects plans with duplicate affected file entries."""
    plan = ImplementationPlan(
        summary="Duplicate Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="app/auth/service.py",
                change_type=ChangeType.MODIFY,
                reason="First update",
            ),
            AffectedFile(
                file_path="app/auth/service.py",
                change_type=ChangeType.MODIFY,
                reason="Second update",
            ),
        ],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "Duplicate file path" in str(exc.value)


def test_plan_validation_excessive_file_count():
    """Rejects plans affecting more than MAX_PLAN_FILES."""
    files = [
        AffectedFile(
            file_path=f"app/module_{i}.py",
            change_type=ChangeType.MODIFY,
            reason=f"Update module {i}",
        )
        for i in range(MAX_PLAN_FILES + 1)
    ]
    plan = ImplementationPlan(
        summary="Large Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=files,
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert f"exceeds maximum limit of {MAX_PLAN_FILES}" in str(exc.value)


def test_plan_validation_excessive_field_length():
    """Rejects plans with excessively long text fields."""
    plan = ImplementationPlan(
        summary="A" * (MAX_PLAN_FIELD_LENGTH + 10),
        problem_statement="Problem",
        approach="Approach",
        affected_files=[],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "exceeds maximum length" in str(exc.value)


def test_plan_validation_empty_required_fields():
    """Rejects plans with empty summary, problem statement, approach, or test strategy."""
    plan = ImplementationPlan(
        summary="",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[],
        test_strategy="Tests",
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan)
    assert "Plan summary cannot be empty" in str(exc.value)


def test_plan_validation_evidence_grounding_requirement():
    """When require_evidence=True, ungrounded modified files are rejected."""
    plan = ImplementationPlan(
        summary="Grounded Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="app/unretrieved_hallucination.py",
                change_type=ChangeType.MODIFY,
                reason="Modify hallucinated file",
            )
        ],
        test_strategy="Tests",
        evidence=[
            AgentSourceReference(
                file_path="app/real_service.py",
                symbol_name="real_function",
            )
        ],
    )

    with pytest.raises(PlanValidationError) as exc:
        validate_implementation_plan(plan, require_evidence=True)
    assert "is not grounded in any retrieved repository evidence" in str(exc.value)


def test_plan_validation_grounded_file_passes():
    """When require_evidence=True, grounded modified files pass validation."""
    plan = ImplementationPlan(
        summary="Grounded Plan",
        problem_statement="Problem",
        approach="Approach",
        affected_files=[
            AffectedFile(
                file_path="app/real_service.py",
                change_type=ChangeType.MODIFY,
                reason="Modify real file",
            )
        ],
        test_strategy="Tests",
        evidence=[
            AgentSourceReference(
                file_path="app/real_service.py",
                symbol_name="real_function",
            )
        ],
    )

    validated = validate_implementation_plan(plan, require_evidence=True)
    assert len(validated.affected_files) == 1
