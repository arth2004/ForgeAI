import asyncio
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.models.agent import TestExecutionStatus
from app.schemas.agent import TestCommand

logger = logging.getLogger(__name__)

# Constants
MAX_OUTPUT_BYTES = 100 * 1024  # 100 KB
MAX_OUTPUT_LINES = 500
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 300

ALLOWED_RUNNERS = {
    "pytest": ["pytest"],
    "ruff": ["ruff", "check"],
    "npm_test": ["npm", "test"],
    "npm_build": ["npm", "run", "build"],
    "cargo_test": ["cargo", "test"],
}

# Regex to detect prohibited shell operators
PROHIBITED_SHELL_PATTERN = re.compile(
    r"[;&|><`$]|(\$\()|(\brm\s+-rf\b)|(\bcurl\b)|(\bwget\b)|(\bbash\b)|(\bsh\b)|(\bpython\s+-c\b)",
    re.IGNORECASE,
)

# Regex to strip ANSI escape sequences
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass
class SandboxExecutionResult:
    status: TestExecutionStatus
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int


def sanitize_command_arguments(runner: str, arguments: list[str]) -> list[str]:
    """Validates and sanitizes declarative test runner arguments, rejecting dangerous shell injections."""
    if runner not in ALLOWED_RUNNERS:
        raise ValidationException(
            f"Unsupported test runner '{runner}'. Allowed runners: {list(ALLOWED_RUNNERS.keys())}"
        )

    clean_args: list[str] = []
    for arg in arguments:
        if not arg or not arg.strip():
            continue
        arg_str = arg.strip()
        if PROHIBITED_SHELL_PATTERN.search(arg_str):
            raise ValidationException(
                f"Prohibited shell character or command operator detected in argument: '{arg_str}'"
            )
        if arg_str.startswith("/") or (len(arg_str) >= 2 and arg_str[1] == ":"):
            raise ValidationException(f"Absolute path arguments are prohibited: '{arg_str}'")
        if ".." in arg_str:
            raise ValidationException(f"Path traversal ('..') is prohibited in argument: '{arg_str}'")
        clean_args.append(arg_str)

    return clean_args


def sanitize_secret_output(text: str) -> str:
    """Redacts known secrets, JWT secrets, encryption keys, and tokens from command output."""
    if not text:
        return ""

    sanitized = text

    # Redact config secrets if present
    secrets_to_scrub = [
        getattr(settings, "JWT_SECRET", None),
        getattr(settings, "ENCRYPTION_KEY", None),
        getattr(settings, "GEMINI_API_KEY", None),
        getattr(settings, "GROQ_API_KEY", None),
        getattr(settings, "OPENAI_API_KEY", None),
        getattr(settings, "DATABASE_URL", None),
        getattr(settings, "REDIS_URL", None),
    ]

    for secret in secrets_to_scrub:
        if secret and len(str(secret)) >= 8:
            sanitized = sanitized.replace(str(secret), "[REDACTED_SECRET]")

    # Redact Bearer tokens and generic API keys
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9\-_.]+", "Bearer [REDACTED_TOKEN]", sanitized)
    sanitized = re.sub(r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/=]{8,}['\"]?", r"\1=[REDACTED]", sanitized)

    return sanitized


def format_and_truncate_output(raw_text: str) -> str:
    """Strips ANSI escapes, redacts secrets, and truncates to 100 KB / 500 lines."""
    if not raw_text:
        return ""

    # Strip ANSI
    text = ANSI_ESCAPE_PATTERN.sub("", raw_text)
    # Sanitize secrets
    text = sanitize_secret_output(text)

    # Line limit
    lines = text.splitlines()
    if len(lines) > MAX_OUTPUT_LINES:
        truncated_lines = lines[:MAX_OUTPUT_LINES]
        text = "\n".join(truncated_lines) + f"\n... [Output truncated after {MAX_OUTPUT_LINES} lines]"

    # Byte limit
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        text = encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore") + "\n... [Output truncated at 100 KB]"

    return text


class SandboxRunner:
    """Manages secure sandboxed test executions inside ephemeral AgentWorkspaces."""

    def __init__(self, fake_runner_override: Any | None = None) -> None:
        self.fake_runner_override = fake_runner_override

    def is_docker_available(self) -> bool:
        """Checks if Docker runtime is available on the host."""
        return shutil.which("docker") is not None

    async def run_test(
        self,
        workspace_path: Path,
        test_command: TestCommand,
    ) -> SandboxExecutionResult:
        """Executes a declarative test runner inside an isolated sandbox or returns SANDBOX_UNAVAILABLE."""
        start_time = time.monotonic()

        # 1. Sanitize arguments
        clean_args = sanitize_command_arguments(test_command.runner, test_command.arguments)
        base_cmd = ALLOWED_RUNNERS[test_command.runner]
        full_command = base_cmd + clean_args
        timeout = min(test_command.timeout_seconds, MAX_TIMEOUT_SECONDS)

        # 2. Check for mock/fake runner override in unit tests
        if self.fake_runner_override:
            return await self.fake_runner_override(workspace_path, full_command, timeout)

        # 3. Check Docker sandbox availability
        if not self.is_docker_available():
            logger.warning("[sandbox.unavailable] Docker runtime is not installed or available on host.")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return SandboxExecutionResult(
                status=TestExecutionStatus.SANDBOX_UNAVAILABLE,
                exit_code=None,
                stdout="",
                stderr="SANDBOX_UNAVAILABLE: Docker sandbox environment is not available on this host. Host execution is strictly prohibited by security policy.",
                duration_ms=duration_ms,
            )

        # 4. Construct containerized execution with strict security isolation
        # --network=none, --memory=2048m, --cpus=2.0, read-write workspace mount, no host secrets
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--memory=2048m",
            "--memory-swap=2560m",
            "--cpus=2.0",
            "-v",
            f"{workspace_path.resolve()}:/workspace:rw",
            "-w",
            "/workspace",
            "python:3.12-slim",
        ] + full_command

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                exit_code = process.returncode
                duration_ms = int((time.monotonic() - start_time) * 1000)
                status = TestExecutionStatus.PASSED if exit_code == 0 else TestExecutionStatus.FAILED

                return SandboxExecutionResult(
                    status=status,
                    exit_code=exit_code,
                    stdout=format_and_truncate_output(stdout_bytes.decode("utf-8", errors="replace")),
                    stderr=format_and_truncate_output(stderr_bytes.decode("utf-8", errors="replace")),
                    duration_ms=duration_ms,
                )

            except TimeoutError:
                logger.warning(f"[sandbox.timeout] Test command timed out after {timeout}s: {full_command}")
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass

                duration_ms = int((time.monotonic() - start_time) * 1000)
                return SandboxExecutionResult(
                    status=TestExecutionStatus.TIMEOUT,
                    exit_code=None,
                    stdout="",
                    stderr=f"TIMEOUT: Test execution exceeded maximum allotted time of {timeout} seconds.",
                    duration_ms=duration_ms,
                )

            except asyncio.CancelledError:
                logger.warning(f"[sandbox.cancelled] Test command was cancelled: {full_command}")
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return SandboxExecutionResult(
                    status=TestExecutionStatus.CANCELLED,
                    exit_code=None,
                    stdout="",
                    stderr="CANCELLED: Test execution was cancelled by client disconnect or abort request.",
                    duration_ms=duration_ms,
                )

        except Exception as e:
            logger.error(f"[sandbox.error] Failed to launch sandbox process: {e}")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return SandboxExecutionResult(
                status=TestExecutionStatus.FAILED,
                exit_code=1,
                stdout="",
                stderr=f"Failed to execute sandboxed command: {e}",
                duration_ms=duration_ms,
            )
