from typing import Any

from app.core.exceptions import UnauthorizedException
from app.models.auth import User
from app.services.github.client import github_client


class GitHubBranchService:
    """Service for discovering and reading branches from an authorized repository."""

    @classmethod
    async def list_branches(
        cls,
        user: User,
        owner: str,
        repo: str,
        default_branch: str = "main",
    ) -> list[dict[str, Any]]:
        """Lists branches for a given repository."""
        if not user.github_installation_id:
            raise UnauthorizedException("GitHub App is not connected.")

        raw_branches = await github_client.list_repository_branches(
            installation_id=user.github_installation_id,
            owner=owner,
            repo=repo,
        )

        formatted_branches = []
        for branch in raw_branches:
            name = branch.get("name", "")
            commit_sha = branch.get("commit", {}).get("sha") if isinstance(branch.get("commit"), dict) else None
            is_protected = branch.get("protected", False)

            formatted_branches.append({
                "name": name,
                "commit_sha": commit_sha,
                "is_protected": is_protected,
                "is_default": name == default_branch,
            })

        return formatted_branches


github_branch_service = GitHubBranchService()
