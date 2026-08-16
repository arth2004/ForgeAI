
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "ok"})
    version: str = Field(..., json_schema_extra={"example": "0.1.0"})
    services: dict[str, str] = Field(
        ...,
        json_schema_extra={
            "example": {
                "database": "ok",
                "redis": "ok",
                "worker_queue": "ok",
            }
        },
    )
    details: dict[str, str] | None = None
