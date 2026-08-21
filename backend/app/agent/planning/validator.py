from typing import Any

from app.agent.exceptions import AgentException
from app.agent.tools.validation import ToolValidationError, validate_safe_file_path
from app.schemas.agent import ChangeType, ImplementationPlan

MAX_PLAN_FILES = 20
MAX_PLAN_FIELD_LENGTH = 10000


class PlanValidationError(AgentException):
    """Raised when an ImplementationPlan fails structural or safety validation."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        det = details or {}
        if field_name:
            det["field_name"] = field_name
        super().__init__(message=message, status_code=400, details=det)


def validate_implementation_plan(
    plan: ImplementationPlan,
    allowed_file_paths: set[str] | None = None,
    require_evidence: bool = False,
) -> ImplementationPlan:
    """Validates an ImplementationPlan against strict safety, size, and grounding rules.

    Rejects:
    - Path traversal (.., absolute paths, null bytes, backslashes)
    - Duplicate affected file paths
    - Unsupported change types
    - Excessive file count (> 20)
    - Excessive string field lengths (> 10000 chars)
    - Ungrounded files when evidence is required
    """
    if not plan.summary or not plan.summary.strip():
        raise PlanValidationError("Plan summary cannot be empty.", field_name="summary")

    if not plan.problem_statement or not plan.problem_statement.strip():
        raise PlanValidationError("Plan problem statement cannot be empty.", field_name="problem_statement")

    if not plan.approach or not plan.approach.strip():
        raise PlanValidationError("Plan approach cannot be empty.", field_name="approach")

    if not plan.test_strategy or not plan.test_strategy.strip():
        raise PlanValidationError("Plan test strategy cannot be empty.", field_name="test_strategy")

    # Length limits
    for field_name, value in [
        ("summary", plan.summary),
        ("problem_statement", plan.problem_statement),
        ("approach", plan.approach),
        ("test_strategy", plan.test_strategy),
    ]:
        if len(value) > MAX_PLAN_FIELD_LENGTH:
            raise PlanValidationError(
                f"Field '{field_name}' exceeds maximum length of {MAX_PLAN_FIELD_LENGTH} characters.",
                field_name=field_name,
            )

    if len(plan.affected_files) > MAX_PLAN_FILES:
        raise PlanValidationError(
            f"Plan affects {len(plan.affected_files)} files, which exceeds maximum limit of {MAX_PLAN_FILES}.",
            field_name="affected_files",
        )

    seen_paths: set[str] = set()
    validated_affected_files = []

    for idx, af in enumerate(plan.affected_files):
        # 1. Validate file path safety
        try:
            safe_path = validate_safe_file_path(af.file_path)
        except ToolValidationError as tve:
            raise PlanValidationError(
                f"Invalid file path '{af.file_path}' in affected_files[{idx}]: {tve.message}",
                field_name=f"affected_files[{idx}].file_path",
            ) from tve

        # 2. Check for duplicate paths
        if safe_path in seen_paths:
            raise PlanValidationError(
                f"Duplicate file path '{safe_path}' found in plan affected_files.",
                field_name="affected_files",
            )
        seen_paths.add(safe_path)

        # 3. Check change type
        if not isinstance(af.change_type, ChangeType):
            try:
                valid_change_type = ChangeType(str(af.change_type).upper())
            except ValueError:
                raise PlanValidationError(
                    f"Unsupported change type '{af.change_type}' for file '{safe_path}'.",
                    field_name=f"affected_files[{idx}].change_type",
                ) from None
        else:
            valid_change_type = af.change_type

        # 4. Check reason
        if not af.reason or not af.reason.strip():
            raise PlanValidationError(
                f"Modification reason cannot be empty for file '{safe_path}'.",
                field_name=f"affected_files[{idx}].reason",
            )

        af.file_path = safe_path
        af.change_type = valid_change_type
        validated_affected_files.append(af)

    plan.affected_files = validated_affected_files

    # Validate new_files and deleted_files lists
    validated_new: list[str] = []
    for nf in plan.new_files:
        try:
            validated_new.append(validate_safe_file_path(nf))
        except ToolValidationError as tve:
            raise PlanValidationError(f"Invalid new file path '{nf}': {tve.message}") from tve
    plan.new_files = validated_new

    validated_deleted: list[str] = []
    for df in plan.deleted_files:
        try:
            validated_deleted.append(validate_safe_file_path(df))
        except ToolValidationError as tve:
            raise PlanValidationError(f"Invalid deleted file path '{df}': {tve.message}") from tve
    plan.deleted_files = validated_deleted

    # Evidence grounding validation
    evidence_paths: set[str] = {ev.file_path for ev in plan.evidence if ev.file_path}
    if allowed_file_paths is not None:
        evidence_paths.update(allowed_file_paths)

    if require_evidence:
        if not plan.evidence and not allowed_file_paths:
            raise PlanValidationError(
                "Plan must be grounded in at least one repository evidence source.",
                field_name="evidence",
            )
        # Check that modified or deleted files are referenced in evidence or allowed files
        for af in plan.affected_files:
            if af.change_type in (ChangeType.MODIFY, ChangeType.DELETE):
                if af.file_path not in evidence_paths:
                    raise PlanValidationError(
                        f"File '{af.file_path}' marked for {af.change_type.value} is not grounded in any retrieved repository evidence.",
                        field_name="affected_files",
                    )

    return plan
