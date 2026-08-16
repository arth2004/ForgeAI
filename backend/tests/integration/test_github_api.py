from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.auth import User
from app.services.github.auth import GitHubAuthService


@pytest.mark.asyncio
async def test_github_status_disconnected(client: AsyncClient, test_user: User, auth_headers: dict[str, str]):
    response = await client.get("/api/v1/github/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["is_connected"] is False
    assert data["github_username"] is None


@pytest.mark.asyncio
async def test_get_github_authorize_url(client: AsyncClient, test_user: User, auth_headers: dict[str, str]):
    response = await client.get("/api/v1/github/authorize", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "state=" in data["authorization_url"]


@pytest.mark.asyncio
async def test_github_callback_invalid_state_redirects_error(client: AsyncClient):
    response = await client.get(
        "/api/v1/github/callback?code=mock_code&state=invalid:tampered:state:sig",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_github_callback_success_connects_user(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    state = GitHubAuthService.generate_state(test_user.id)

    mock_profile = {
        "id": 88881234,
        "login": "octocat-dev",
        "avatar_url": "https://avatars.githubusercontent.com/u/88881234",
    }

    with patch("app.services.github.auth.GitHubAuthService.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
         patch("app.services.github.client.github_client.get_user_profile", new_callable=AsyncMock) as mock_get_profile, \
         patch("app.services.github.client.github_client.get_user_installations", new_callable=AsyncMock) as mock_get_inst:

        mock_exchange.return_value = "ghu_mock_user_token"
        mock_get_profile.return_value = mock_profile
        mock_get_inst.return_value = [{"id": 554433}]

        response = await client.get(
            f"/api/v1/github/callback?code=valid_code&state={state}&installation_id=554433",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "github=connected" in response.headers["location"]

        # Check status endpoint now reflects connection
        status_resp = await client.get("/api/v1/github/status", headers=auth_headers)
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["is_connected"] is True
        assert data["github_username"] == "octocat-dev"
        assert data["github_installation_id"] == 554433


@pytest.mark.asyncio
async def test_list_github_repositories(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    # Connect user with installation
    test_user.github_installation_id = 554433
    test_user.github_username = "octocat-dev"

    mock_repos_payload = {
        "total_count": 1,
        "repositories": [
            {
                "id": 1234567,
                "name": "forge-engine",
                "full_name": "octocat-dev/forge-engine",
                "owner": {"login": "octocat-dev"},
                "private": True,
                "default_branch": "main",
                "html_url": "https://github.com/octocat-dev/forge-engine",
                "description": "Core engine",
                "language": "Python",
                "updated_at": "2026-08-16T12:00:00Z",
            }
        ],
    }

    with patch("app.services.github.client.github_client.list_installation_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_repos_payload

        response = await client.get("/api/v1/github/repositories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["repositories"]) == 1
        repo = data["repositories"][0]
        assert repo["name"] == "forge-engine"
        assert repo["is_private"] is True
        assert "token" not in str(data)  # Security: No token exposed


@pytest.mark.asyncio
async def test_list_github_branches(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    test_user.github_installation_id = 554433

    mock_branches_payload = [
        {"name": "main", "commit": {"sha": "abc1234567890abcdef"}, "protected": True},
        {"name": "feature/ai-agent", "commit": {"sha": "fedcba0987654321"}, "protected": False},
    ]

    with patch("app.services.github.client.github_client.list_repository_branches", new_callable=AsyncMock) as mock_branches:
        mock_branches.return_value = mock_branches_payload

        response = await client.get(
            "/api/v1/github/repositories/octocat-dev/forge-engine/branches?default_branch=main",
            headers=auth_headers,
        )
        assert response.status_code == 200
        branches = response.json()
        assert len(branches) == 2
        assert branches[0]["name"] == "main"
        assert branches[0]["is_default"] is True
        assert branches[0]["is_protected"] is True


@pytest.mark.asyncio
async def test_create_project_from_github_repository(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    # 1. Create Organization
    org_resp = await client.post("/api/v1/organizations", json={"name": "Engineering Org"}, headers=auth_headers)
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    # 2. Create Project from GitHub Repository
    payload = {
        "organization_id": org_id,
        "project_name": "Forge Engine AI",
        "project_description": "AI Workspace",
        "github_repo_id": 1234567,
        "full_name": "octocat-dev/forge-engine",
        "owner": "octocat-dev",
        "default_branch": "main",
        "selected_branch": "main",
        "latest_commit_sha": "abc1234567890abcdef",
        "is_private": True,
        "html_url": "https://github.com/octocat-dev/forge-engine",
        "description": "Core engine",
        "language": "Python",
    }

    response = await client.post(
        "/api/v1/github/projects/create-from-repo",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["project"]["name"] == "Forge Engine AI"
    assert data["repository"]["full_name"] == "octocat-dev/forge-engine"
    assert data["repository"]["indexing_status"] == "pending"
    assert data["selected_branch"]["name"] == "main"
    assert data["selected_branch"]["latest_commit_sha"] == "abc1234567890abcdef"
    assert data["status"] == "pending"
    assert "token" not in str(data)  # Security: No token exposed


@pytest.mark.asyncio
async def test_disconnect_github_clears_credentials(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    test_user.github_installation_id = 554433
    test_user.github_username = "octocat-dev"

    response = await client.delete("/api/v1/github/disconnect", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["is_connected"] is False

    status_resp = await client.get("/api/v1/github/status", headers=auth_headers)
    assert status_resp.json()["is_connected"] is False
