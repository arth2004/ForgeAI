from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.auth import User
from app.models.project import RepositoryBranch
from app.schemas.github import (
    CreateProjectFromGitHubRequest,
    GitHubAuthUrlResponse,
    GitHubBranchResponse,
    GitHubProjectCreationResponse,
    GitHubRepositoryListResponse,
    GitHubRepositoryResponse,
    GitHubStatusResponse,
)
from app.schemas.project import ProjectCreate, ProjectResponse
from app.schemas.repository import RepositoryBranchResponse, RepositoryCreate, RepositoryResponse
from app.services.github.auth import github_auth_service
from app.services.github.branches import github_branch_service
from app.services.github.repositories import github_repository_service
from app.services.project_service import ProjectService
from app.services.repository_service import RepositoryService

router = APIRouter()


@router.get(
    "/authorize",
    response_model=GitHubAuthUrlResponse,
    summary="Get GitHub App installation and authorization URL",
)
async def get_github_authorize_url(
    current_user: Annotated[User, Depends(get_current_user)],
) -> GitHubAuthUrlResponse:
    """Generates an authorization URL with a cryptographically signed CSRF state."""
    auth_url = github_auth_service.get_authorization_url(current_user.id)
    return GitHubAuthUrlResponse(authorization_url=auth_url)


@router.get(
    "/callback",
    summary="Handle GitHub App authorization / installation callback",
)
async def github_oauth_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = Query(None),
    installation_id: int | None = Query(None),
    state: str | None = Query(None),
) -> RedirectResponse:
    """Validates CSRF state and connects the GitHub account to the local user."""
    if not state:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?error=missing_state",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        user_id = github_auth_service.validate_state(state)
        await github_auth_service.connect_user_github(
            db=db,
            user_id=user_id,
            code=code,
            installation_id=installation_id,
        )
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?github=connected",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?error={type(e).__name__}",
            status_code=status.HTTP_302_FOUND,
        )


@router.get(
    "/status",
    response_model=GitHubStatusResponse,
    summary="Get current user's GitHub connection status",
)
async def get_github_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> GitHubStatusResponse:
    """Returns whether the current user has connected their GitHub account."""
    is_connected = bool(current_user.github_installation_id or current_user.github_user_id)
    return GitHubStatusResponse(
        is_connected=is_connected,
        github_user_id=current_user.github_user_id,
        github_username=current_user.github_username,
        github_installation_id=current_user.github_installation_id,
        avatar_url=current_user.avatar_url,
    )


@router.delete(
    "/disconnect",
    response_model=GitHubStatusResponse,
    summary="Disconnect GitHub account",
)
async def disconnect_github(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GitHubStatusResponse:
    """Revokes stored GitHub credentials and unlinks the GitHub identity."""
    await github_auth_service.disconnect_user_github(db=db, user_id=current_user.id)
    return GitHubStatusResponse(is_connected=False)


@router.get(
    "/repositories",
    response_model=GitHubRepositoryListResponse,
    summary="List repositories authorized for Forge AI",
)
async def list_github_repositories(
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
) -> GitHubRepositoryListResponse:
    """Returns paginated repositories explicitly granted to this user's installation."""
    repos, total_count = await github_repository_service.list_repositories(
        user=current_user,
        page=page,
        per_page=per_page,
    )
    return GitHubRepositoryListResponse(
        repositories=[GitHubRepositoryResponse(**r) for r in repos],
        total_count=total_count,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/repositories/{owner}/{repo}/branches",
    response_model=list[GitHubBranchResponse],
    summary="List branches for an authorized repository",
)
async def list_github_repository_branches(
    owner: str,
    repo: str,
    current_user: Annotated[User, Depends(get_current_user)],
    default_branch: str = Query("main"),
) -> list[GitHubBranchResponse]:
    """Retrieves branches for the selected repository."""
    branches = await github_branch_service.list_branches(
        user=current_user,
        owner=owner,
        repo=repo,
        default_branch=default_branch,
    )
    return [GitHubBranchResponse(**b) for b in branches]


@router.post(
    "/projects/create-from-repo",
    response_model=GitHubProjectCreationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Forge Project from an authorized GitHub repository",
)
async def create_project_from_github_repository(
    payload: CreateProjectFromGitHubRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GitHubProjectCreationResponse:
    """Atomic creation of a Project, Repository, and RepositoryBranch from a GitHub repository."""
    project_svc = ProjectService(db)
    repo_svc = RepositoryService(db)

    # 1. Create Forge Project (enforces tenant membership authorization)
    project_data = ProjectCreate(
        organization_id=payload.organization_id,
        name=payload.project_name,
        description=payload.project_description,
    )
    project = await project_svc.create(user_id=current_user.id, data=project_data)

    # 2. Create Repository record linked to Project
    repo_data = RepositoryCreate(
        project_id=project.id,
        github_repo_id=payload.github_repo_id,
        owner=payload.owner,
        full_name=payload.full_name,
        default_branch=payload.default_branch,
        is_private=payload.is_private,
        html_url=payload.html_url,
        description=payload.description,
        language=payload.language,
    )
    repo = await repo_svc.create(user_id=current_user.id, data=repo_data)

    # Update rich metadata fields
    repo.owner = payload.owner
    repo.html_url = payload.html_url
    repo.description = payload.description
    repo.language = payload.language

    # 3. Create or resolve selected RepositoryBranch
    branch_stmt = select(RepositoryBranch).where(
        RepositoryBranch.repository_id == repo.id,
        RepositoryBranch.name == payload.selected_branch,
    )
    res = await db.execute(branch_stmt)
    branch = res.scalar_one_or_none()

    if not branch:
        branch = RepositoryBranch(
            repository_id=repo.id,
            name=payload.selected_branch,
            latest_commit_sha=payload.latest_commit_sha,
        )
        db.add(branch)
        await db.flush()
    elif payload.latest_commit_sha:
        branch.latest_commit_sha = payload.latest_commit_sha
        await db.flush()

    await db.commit()
    await db.refresh(project)
    await db.refresh(repo)
    await db.refresh(branch)

    return GitHubProjectCreationResponse(
        project=ProjectResponse.model_validate(project),
        repository=RepositoryResponse.model_validate(repo),
        selected_branch=RepositoryBranchResponse.model_validate(branch),
        status="pending",
        message="Repository successfully connected to project. Ready for indexing.",
    )
