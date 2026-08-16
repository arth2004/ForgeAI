import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    organization_id: uuid.UUID
    settings: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None = None
    settings: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
