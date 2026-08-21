import pytest

from app.core.exceptions import ValidationException
from app.services.git_service import sanitize_branch_name, scrub_sensitive_tokens
from app.services.github_pr_service import sanitize_pr_markdown


def test_sanitize_branch_name_valid():
    """Accepts valid alphanumeric and hierarchical branch names."""
    valid_names = [
        "forge/session-123",
        "forge/issue-42-fix-auth",
        "feature/add-logging",
        "bugfix_issue_99",
        "user.feature-1",
    ]
    for name in valid_names:
        assert sanitize_branch_name(name) == name


@pytest.mark.parametrize(
    "protected_name",
    [
        "main",
        "master",
        "production",
        "prod",
        "staging",
        "develop",
        "release",
        "release/v1.0.0",
        "releases/2026-08",
    ],
)
def test_sanitize_branch_name_protected_rejected(protected_name: str):
    """Rejects protected production and release branch targets."""
    with pytest.raises(ValidationException) as exc:
        sanitize_branch_name(protected_name)
    assert "protected" in str(exc.value).lower()


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "branch with spaces",
        "branch..traversal",
        "branch//double-slash",
        "/leading-slash",
        "trailing-slash/",
        "branch.lock",
        "branch;rm -rf",
        "branch`whoami`",
        "branch$FOO",
    ],
)
def test_sanitize_branch_name_invalid_chars_rejected(invalid_name: str):
    """Rejects empty, path traversal, or command injection attempts in branch names."""
    with pytest.raises(ValidationException):
        sanitize_branch_name(invalid_name)


def test_scrub_sensitive_tokens():
    """Redacts GitHub App tokens from command output strings."""
    sample = "remote: pushing to https://x-access-token:ghs_1234567890abcdef1234567890@github.com/org/repo.git"
    scrubbed = scrub_sensitive_tokens(sample)
    assert "ghs_1234567890abcdef1234567890" not in scrubbed
    assert "x-access-token:[REDACTED]@" in scrubbed


def test_sanitize_pr_markdown():
    """Sanitizes script tags from PR bodies while preserving Markdown formatting."""
    raw_body = "## Summary\nFixed bug.\n<script>alert('pwned')</script>\n```python\nprint(1)\n```"
    sanitized = sanitize_pr_markdown(raw_body)
    assert "<script>" not in sanitized
    assert "Fixed bug." in sanitized
    assert "```python" in sanitized
