import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import IndexingStatus


class RepositoryCreate(BaseModel):
    project_id: uuid.UUID
    full_name: str = Field(..., min_length=3, max_length=255, json_schema_extra={"example": "facebook/react"})
    default_branch: str = Field(default="main")
    is_private: bool = Field(default=False)
    github_repo_id: int | None = None


class RepositoryBranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    name: str
    latest_commit_sha: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    github_repo_id: int | None = None
    full_name: str
    default_branch: str
    is_private: bool
    indexing_status: IndexingStatus
    created_at: datetime
    updated_at: datetime
