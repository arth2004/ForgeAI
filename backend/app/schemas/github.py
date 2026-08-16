import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.project import ProjectResponse
from app.schemas.repository import RepositoryBranchResponse, RepositoryResponse


class GitHubAuthUrlResponse(BaseModel):
    authorization_url: str


class GitHubStatusResponse(BaseModel):
    is_connected: bool
    github_user_id: int | None = None
    github_username: str | None = None
    github_installation_id: int | None = None
    avatar_url: str | None = None


class GitHubRepositoryResponse(BaseModel):
    github_repo_id: int
    name: str
    full_name: str
    owner: str | None = None
    is_private: bool = False
    default_branch: str = "main"
    html_url: str | None = None
    description: str | None = None
    language: str | None = None
    updated_at: str | None = None


class GitHubRepositoryListResponse(BaseModel):
    repositories: list[GitHubRepositoryResponse]
    total_count: int
    page: int
    per_page: int


class GitHubBranchResponse(BaseModel):
    name: str
    commit_sha: str | None = None
    is_protected: bool = False
    is_default: bool = False


class CreateProjectFromGitHubRequest(BaseModel):
    organization_id: uuid.UUID
    project_name: str = Field(..., min_length=1, max_length=255)
    project_description: str | None = None
    github_repo_id: int
    full_name: str = Field(..., min_length=1, max_length=255)
    owner: str | None = None
    default_branch: str = "main"
    selected_branch: str = "main"
    latest_commit_sha: str | None = None
    is_private: bool = False
    html_url: str | None = None
    description: str | None = None
    language: str | None = None


class GitHubProjectCreationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    repository: RepositoryResponse
    selected_branch: RepositoryBranchResponse
    status: str = "pending"
    message: str = "Repository successfully connected to project. Ready for indexing."
