import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.models.auth import User
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.organization_service import OrganizationService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    organization_id: uuid.UUID | None = Query(None, description="Filter by Organization ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects for an organization or all accessible organizations."""
    project_service = ProjectService(db)
    org_service = OrganizationService(db)

    if organization_id:
        return await project_service.list_for_org(current_user.id, organization_id)

    # List across all orgs user belongs to
    orgs = await org_service.list_for_user(current_user.id)
    all_projects = []
    for org in orgs:
        projects = await project_service.list_for_org(current_user.id, org.id)
        all_projects.extend(projects)
    return all_projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project within an organization."""
    project_service = ProjectService(db)
    return await project_service.create(current_user.id, data)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details by ID."""
    project_service = ProjectService(db)
    project = await project_service.get_by_id(current_user.id, project_id)
    if not project:
        raise NotFoundException("Project", project_id)
    return project
