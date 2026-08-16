from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.github import router as github_router
from app.api.v1.health import router as health_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.projects import router as projects_router
from app.api.v1.repositories import router as repositories_router
from app.api.v1.worker import router as worker_router

api_router = APIRouter()

# Register sub-routers under /api/v1
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(github_router, prefix="/github", tags=["GitHub Integration"])
api_router.include_router(organizations_router)
api_router.include_router(projects_router)
api_router.include_router(repositories_router)
api_router.include_router(worker_router)
