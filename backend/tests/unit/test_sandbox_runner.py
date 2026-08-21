from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.models.agent import TestExecutionStatus
from app.schemas.agent import TestCommand
from app.services.sandbox.runner import (
    ALLOWED_RUNNERS,
    MAX_OUTPUT_BYTES,
    MAX_OUTPUT_LINES,
    SandboxExecutionResult,
    SandboxRunner,
    format_and_truncate_output,
    sanitize_command_arguments,
    sanitize_secret_output,
)


def test_allowed_runners_validation():
    """Allows standard declarative runners and clean arguments."""
    for runner in ALLOWED_RUNNERS:
        args = sanitize_command_arguments(runner, ["tests/test_auth.py", "-v", "--tb=short"])
        assert len(args) == 3


def test_unsupported_runner_rejection():
    """Rejects arbitrary or unsupported runners."""
    with pytest.raises(ValidationException) as exc:
        sanitize_command_arguments("bash", ["script.sh"])
    assert "Unsupported test runner 'bash'" in str(exc.value)


@pytest.mark.parametrize(
    "bad_arg",
    [
        "test.py; rm -rf /",
        "test.py && echo evil",
        "test.py || echo evil",
        "test.py | grep foo",
        "test.py > out.txt",
        "`whoami`",
        "$(whoami)",
        "curl http://evil.com",
        "bash -c evil",
        "python -c 'import os'",
    ],
)
def test_prohibited_shell_operators_rejection(bad_arg: str):
    """Rejects arguments containing shell injection characters or dangerous commands."""
    with pytest.raises(ValidationException) as exc:
        sanitize_command_arguments("pytest", [bad_arg])
    assert "Prohibited shell character or command operator" in str(exc.value)


def test_argument_path_traversal_rejection():
    """Rejects path traversal in test arguments."""
    with pytest.raises(ValidationException) as exc:
        sanitize_command_arguments("pytest", ["../../tests/test_auth.py"])
    assert "Path traversal ('..') is prohibited" in str(exc.value)


def test_argument_absolute_path_rejection():
    """Rejects absolute paths in test arguments."""
    with pytest.raises(ValidationException) as exc:
        sanitize_command_arguments("pytest", ["/etc/passwd"])
    assert "Absolute path arguments are prohibited" in str(exc.value)


def test_secret_sanitization():
    """Redacts bearer tokens and generic API keys from output."""
    sample_output = (
        "Traceback:\n"
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz.abc\n"
        "api_key = 'sk-1234567890abcdef12345'\n"
        "DATABASE_URL='postgresql://user:secretpassword123@localhost/db'\n"
    )
    sanitized = sanitize_secret_output(sample_output)
    assert "eyJhbGciOiJIUzI1Ni" not in sanitized
    assert "Bearer [REDACTED_TOKEN]" in sanitized
    assert "sk-1234567890abcdef12345" not in sanitized


def test_output_truncation_lines_and_bytes():
    """Truncates output exceeding 500 lines or 100 KB."""
    # 1. Line limit
    many_lines = "\n".join(f"Log line {i}" for i in range(MAX_OUTPUT_LINES + 50))
    formatted = format_and_truncate_output(many_lines)
    assert f"Output truncated after {MAX_OUTPUT_LINES} lines" in formatted

    # 2. Byte limit
    huge_text = "A" * (MAX_OUTPUT_BYTES + 5000)
    formatted_bytes = format_and_truncate_output(huge_text)
    assert "Output truncated at 100 KB" in formatted_bytes


@pytest.mark.asyncio
async def test_sandbox_unavailable_when_no_docker(tmp_path: Path):
    """When Docker is not available, returns SANDBOX_UNAVAILABLE and does NOT run on host."""
    runner = SandboxRunner()
    # Force is_docker_available to return False
    runner.is_docker_available = lambda: False  # type: ignore

    cmd = TestCommand(runner="pytest", arguments=["tests/test_auth.py"])
    res = await runner.run_test(tmp_path, cmd)

    assert res.status == TestExecutionStatus.SANDBOX_UNAVAILABLE
    assert res.exit_code is None
    assert "Docker sandbox environment is not available on this host" in res.stderr


@pytest.mark.asyncio
async def test_sandbox_fake_runner_override(tmp_path: Path):
    """Verifies fake runner override executes deterministically in tests."""
    async def mock_fake_run(ws_path, command, timeout):
        return SandboxExecutionResult(
            status=TestExecutionStatus.PASSED,
            exit_code=0,
            stdout="================ 5 passed in 0.42s ================",
            stderr="",
            duration_ms=420,
        )

    runner = SandboxRunner(fake_runner_override=mock_fake_run)
    cmd = TestCommand(runner="pytest", arguments=["tests/test_sample.py"])
    res = await runner.run_test(tmp_path, cmd)

    assert res.status == TestExecutionStatus.PASSED
    assert res.exit_code == 0
    assert "5 passed" in res.stdout
