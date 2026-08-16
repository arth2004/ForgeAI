import datetime
import uuid

from pydantic import BaseModel, Field


class TriggerIndexingRequest(BaseModel):
    branch_id: uuid.UUID | None = Field(
        default=None, description="Target branch ID to index (defaults to default branch)"
    )
    is_full_reindex: bool = Field(
        default=False, description="Whether to purge and re-index the full branch"
    )


class IndexingJobResponse(BaseModel):
    job_id: uuid.UUID
    repository_id: uuid.UUID
    branch_id: uuid.UUID
    index_version_id: uuid.UUID | None = None
    commit_sha: str
    status: str
    total_files: int
    processed_files: int
    total_chunks: int
    embedded_chunks: int
    error_message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    branch_id: uuid.UUID | None = None
    top_k: int = Field(default=15, ge=1, le=100)


class EvidenceChunkResponse(BaseModel):
    chunk_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None = None
    chunk_type: str
    context_header: str
    content: str
    rrf_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    symbol_rank: int | None = None
    commit_sha: str
    branch_name: str
    index_version_id: uuid.UUID | None = None
    repository_id: uuid.UUID | None = None


class HybridSearchResponse(BaseModel):
    query: str
    total_results: int
    results: list[EvidenceChunkResponse]


class RepositoryFileResponse(BaseModel):
    id: uuid.UUID
    file_path: str
    file_name: str
    extension: str
    language: str
    size_bytes: int
    content_hash: str
    chunks_count: int


class RepositoryFileDetailResponse(BaseModel):
    id: uuid.UUID
    file_path: str
    file_name: str
    language: str
    size_bytes: int
    content_hash: str
    chunks: list[EvidenceChunkResponse]
