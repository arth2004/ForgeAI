import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.redis import get_arq_pool
from app.core.telemetry import logger
from app.models.auth import Membership, User
from app.models.codebase import (
    IndexingJob,
    IndexingJobStatus,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import Project, Repository, RepositoryBranch
from app.schemas.ingestion import (
    EvidenceChunkResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    IndexingJobResponse,
    RepositoryFileDetailResponse,
    RepositoryFileResponse,
    TriggerIndexingRequest,
)
from app.services.ingestion.engine import IngestionEngine
from app.services.retrieval.hybrid import HybridSearchEngine

router = APIRouter(prefix="/projects/{project_id}", tags=["Ingestion & Search"])


async def verify_project_access(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Project:
    """Helper ensuring the user belongs to the project's organization."""
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundException("Project", project_id)

    membership_q = select(Membership).where(
        Membership.organization_id == project.organization_id,
        Membership.user_id == user_id,
    )
    membership_res = await db.execute(membership_q)
    if not membership_res.scalars().first():
        raise ForbiddenException("You do not have access to this project.")

    return project


@router.post(
    "/repositories/{repo_id}/index",
    response_model=IndexingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_repository_indexing(
    project_id: uuid.UUID,
    repo_id: uuid.UUID,
    data: TriggerIndexingRequest = TriggerIndexingRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Triggers background repository indexing (full or incremental) for a repository branch."""
    await verify_project_access(project_id, current_user.id, db)

    repo = await db.get(Repository, repo_id)
    if not repo or repo.project_id != project_id:
        raise NotFoundException("Repository", repo_id)

    # Determine branch
    branch_id = data.branch_id
    if not branch_id:
        branch_q = select(RepositoryBranch).where(
            RepositoryBranch.repository_id == repo_id,
            RepositoryBranch.name == repo.default_branch,
        )
        branch_res = await db.execute(branch_q)
        branch = branch_res.scalars().first()
        if not branch:
            # Fallback to any branch for repo
            branch_q = select(RepositoryBranch).where(RepositoryBranch.repository_id == repo_id)
            branch = (await db.execute(branch_q)).scalars().first()
            if not branch:
                raise NotFoundException("RepositoryBranch", "default")
        branch_id = branch.id

    # Concurrency guard: return existing in-flight job if already running
    active_job_q = (
        select(IndexingJob)
        .where(
            IndexingJob.repository_id == repo_id,
            IndexingJob.branch_id == branch_id,
            IndexingJob.status.in_(
                [
                    IndexingJobStatus.PENDING,
                    IndexingJobStatus.ACQUIRING,
                    IndexingJobStatus.PARSING,
                    IndexingJobStatus.EMBEDDING,
                    IndexingJobStatus.INDEXING,
                ]
            ),
        )
        .order_by(desc(IndexingJob.created_at))
        .limit(1)
    )
    active_job = (await db.execute(active_job_q)).scalars().first()
    if active_job:
        logger.info(
            f"Indexing job {active_job.id} is already in progress for repo {repo_id}, branch {branch_id}"
        )
        return IndexingJobResponse(
            job_id=active_job.id,
            repository_id=active_job.repository_id,
            branch_id=active_job.branch_id,
            index_version_id=active_job.index_version_id,
            commit_sha=active_job.commit_sha,
            status=active_job.status.value
            if hasattr(active_job.status, "value")
            else str(active_job.status),
            total_files=active_job.total_files,
            processed_files=active_job.processed_files,
            total_chunks=active_job.total_chunks,
            embedded_chunks=active_job.embedded_chunks,
            error_message=active_job.error_message,
            started_at=active_job.started_at,
            completed_at=active_job.completed_at,
            created_at=active_job.created_at,
        )

    # Create initial IndexingJob record
    job = IndexingJob(
        repository_id=repo_id,
        branch_id=branch_id,
        commit_sha=repo.default_branch,
        status=IndexingJobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue indexing task to ARQ Redis worker queue
    try:
        arq_pool = await get_arq_pool()
        await arq_pool.enqueue_job(
            "index_repository_task",
            str(repo_id),
            str(branch_id),
            is_full_reindex=data.is_full_reindex,
            job_id=str(job.id),
        )
    except Exception as e:
        logger.warning(
            f"ARQ queue unavailable ({e}). Falling back to local asynchronous indexing task."
        )
        import asyncio

        asyncio.create_task(
            IngestionEngine.run_indexing(
                repository_id=repo_id,
                branch_id=branch_id,
                is_full_reindex=data.is_full_reindex,
                job_id=job.id,
            )
        )

    return IndexingJobResponse(
        job_id=job.id,
        repository_id=job.repository_id,
        branch_id=job.branch_id,
        index_version_id=job.index_version_id,
        commit_sha=job.commit_sha,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        total_files=job.total_files,
        processed_files=job.processed_files,
        total_chunks=job.total_chunks,
        embedded_chunks=job.embedded_chunks,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


@router.get(
    "/repositories/{repo_id}/index/status",
    response_model=IndexingJobResponse,
)
async def get_repository_indexing_status(
    project_id: uuid.UUID,
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves the latest indexing job progress and telemetry for a repository."""
    await verify_project_access(project_id, current_user.id, db)

    job_q = (
        select(IndexingJob)
        .where(IndexingJob.repository_id == repo_id)
        .order_by(desc(IndexingJob.created_at))
        .limit(1)
    )
    job_res = await db.execute(job_q)
    job = job_res.scalars().first()

    if not job:
        raise NotFoundException("IndexingJob for repository", repo_id)

    return IndexingJobResponse(
        job_id=job.id,
        repository_id=job.repository_id,
        branch_id=job.branch_id,
        index_version_id=job.index_version_id,
        commit_sha=job.commit_sha,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        total_files=job.total_files,
        processed_files=job.processed_files,
        total_chunks=job.total_chunks,
        embedded_chunks=job.embedded_chunks,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


@router.post(
    "/search/hybrid",
    response_model=HybridSearchResponse,
)
async def search_repository_hybrid(
    project_id: uuid.UUID,
    data: HybridSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Executes 3-stage hybrid search (dense pgvector + sparse full-text + symbol match with RRF)."""
    await verify_project_access(project_id, current_user.id, db)

    evidence_chunks = await HybridSearchEngine.search(
        project_id=project_id,
        query=data.query,
        branch_id=data.branch_id,
        top_k=data.top_k,
        session_override=db,
    )

    results = [
        EvidenceChunkResponse(
            chunk_id=c.chunk_id,
            file_path=c.file_path,
            start_line=c.start_line,
            end_line=c.end_line,
            symbol_name=c.symbol_name,
            chunk_type=c.chunk_type,
            context_header=c.context_header,
            content=c.content,
            rrf_score=c.rrf_score,
            dense_rank=c.dense_rank,
            sparse_rank=c.sparse_rank,
            symbol_rank=c.symbol_rank,
            commit_sha=c.commit_sha,
            branch_name=c.branch_name,
            index_version_id=c.index_version_id,
            repository_id=c.repository_id,
        )
        for c in evidence_chunks
    ]

    return HybridSearchResponse(
        query=data.query,
        total_results=len(results),
        results=results,
    )


@router.get(
    "/files",
    response_model=list[RepositoryFileResponse],
)
async def list_indexed_files(
    project_id: uuid.UUID,
    branch_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists indexed files and chunk counts for the active index version."""
    await verify_project_access(project_id, current_user.id, db)

    active_ver_q = (
        select(RepositoryIndexVersion)
        .join(Repository, Repository.id == RepositoryIndexVersion.repository_id)
        .where(
            Repository.project_id == project_id,
            RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
        )
    )
    if branch_id:
        active_ver_q = active_ver_q.where(RepositoryIndexVersion.branch_id == branch_id)

    active_versions = (await db.execute(active_ver_q)).scalars().all()
    if not active_versions:
        return []

    active_ver_ids = [v.id for v in active_versions]

    files_q = (
        select(RepositoryFile)
        .where(RepositoryFile.index_version_id.in_(active_ver_ids))
        .options(selectinload(RepositoryFile.chunks))
        .order_by(RepositoryFile.file_path)
    )
    files_res = await db.execute(files_q)
    files = files_res.scalars().all()

    return [
        RepositoryFileResponse(
            id=f.id,
            file_path=f.file_path,
            file_name=f.file_name,
            extension=f.extension,
            language=f.language,
            size_bytes=f.size_bytes,
            content_hash=f.content_hash,
            chunks_count=len(f.chunks),
        )
        for f in files
    ]


@router.get(
    "/files/{file_id}",
    response_model=RepositoryFileDetailResponse,
)
async def get_file_detail(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves file details and its parsed chunks."""
    await verify_project_access(project_id, current_user.id, db)

    file_q = (
        select(RepositoryFile)
        .where(RepositoryFile.id == file_id)
        .options(
            selectinload(RepositoryFile.chunks),
            selectinload(RepositoryFile.index_version).selectinload(RepositoryIndexVersion.branch),
        )
    )
    file_obj = (await db.execute(file_q)).scalars().first()
    if not file_obj:
        raise NotFoundException("RepositoryFile", file_id)

    branch_name = (
        file_obj.index_version.branch.name
        if file_obj.index_version and file_obj.index_version.branch
        else ""
    )
    commit_sha = file_obj.index_version.commit_sha if file_obj.index_version else ""

    chunks = [
        EvidenceChunkResponse(
            chunk_id=c.id,
            file_path=file_obj.file_path,
            start_line=c.start_line,
            end_line=c.end_line,
            symbol_name=c.symbol_name,
            chunk_type=c.chunk_type.value if hasattr(c.chunk_type, "value") else str(c.chunk_type),
            context_header=c.context_header,
            content=c.content,
            rrf_score=1.0,
            commit_sha=commit_sha,
            branch_name=branch_name,
            index_version_id=c.index_version_id,
            repository_id=c.repository_id,
        )
        for c in file_obj.chunks
    ]

    return RepositoryFileDetailResponse(
        id=file_obj.id,
        file_path=file_obj.file_path,
        file_name=file_obj.file_name,
        language=file_obj.language,
        size_bytes=file_obj.size_bytes,
        content_hash=file_obj.content_hash,
        chunks=chunks,
    )
