from typing import Any

from app.core.exceptions import UnauthorizedException
from app.models.auth import User
from app.services.github.client import github_client


class GitHubRepositoryService:
    """Service for discovering and reading repositories accessible to the user's GitHub App installation."""

    @classmethod
    async def list_repositories(
        cls,
        user: User,
        page: int = 1,
        per_page: int = 30,
    ) -> tuple[list[dict[str, Any]], int]:
        """Lists repositories granted to the user's GitHub App installation."""
        if not user.github_installation_id:
            raise UnauthorizedException("GitHub App is not connected. Please connect your GitHub account in Settings.")

        data = await github_client.list_installation_repositories(
            installation_id=user.github_installation_id,
            page=page,
            per_page=per_page,
        )

        total_count = data.get("total_count", 0)
        raw_repos = data.get("repositories", [])

        formatted_repos = []
        for repo in raw_repos:
            formatted_repos.append({
                "github_repo_id": repo["id"],
                "name": repo["name"],
                "full_name": repo["full_name"],
                "owner": repo["owner"]["login"] if "owner" in repo and "login" in repo["owner"] else None,
                "is_private": repo.get("private", False),
                "default_branch": repo.get("default_branch", "main"),
                "html_url": repo.get("html_url"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "updated_at": repo.get("updated_at"),
            })

        return formatted_repos, total_count

    @classmethod
    async def get_repository_details(
        cls,
        user: User,
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        """Fetches detailed repository information."""
        if not user.github_installation_id:
            raise UnauthorizedException("GitHub App is not connected.")

        raw_repo = await github_client.get_repository(
            installation_id=user.github_installation_id,
            owner=owner,
            repo=repo,
        )

        return {
            "github_repo_id": raw_repo["id"],
            "name": raw_repo["name"],
            "full_name": raw_repo["full_name"],
            "owner": raw_repo["owner"]["login"] if "owner" in raw_repo else owner,
            "is_private": raw_repo.get("private", False),
            "default_branch": raw_repo.get("default_branch", "main"),
            "html_url": raw_repo.get("html_url"),
            "description": raw_repo.get("description"),
            "language": raw_repo.get("language"),
            "updated_at": raw_repo.get("updated_at"),
        }


github_repository_service = GitHubRepositoryService()
