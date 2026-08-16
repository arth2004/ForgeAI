import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.models.auth import User
from app.schemas.repository import RepositoryCreate, RepositoryResponse
from app.services.repository_service import RepositoryService

router = APIRouter(tags=["Repositories"])


@router.get("/projects/{project_id}/repositories", response_model=list[RepositoryResponse])
async def list_repositories(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all repositories connected to a project."""
    service = RepositoryService(db)
    return await service.list_for_project(current_user.id, project_id)


@router.post("/projects/{project_id}/repositories", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def connect_repository(
    project_id: uuid.UUID,
    data: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect a repository to a project."""
    # Ensure project_id matches path
    data.project_id = project_id
    service = RepositoryService(db)
    return await service.create(current_user.id, data)


@router.get("/projects/{project_id}/repositories/{repo_id}", response_model=RepositoryResponse)
async def get_repository(
    project_id: uuid.UUID,
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get repository details."""
    service = RepositoryService(db)
    repo = await service.get_by_id(current_user.id, repo_id)
    if not repo or repo.project_id != project_id:
        raise NotFoundException("Repository", repo_id)
    return repo
