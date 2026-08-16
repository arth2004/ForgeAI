import datetime
import logging
import os
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ForgeAIException, NotFoundException
from app.models.codebase import (
    ChunkEmbedding,
    CodeChunk,
    CodeDependency,
    IndexingJob,
    IndexingJobStatus,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import IndexingStatus, Repository, RepositoryBranch
from app.services.embedding.factory import get_embedding_provider
from app.services.github.client import github_client
from app.services.ingestion.differ import IndexDiffer
from app.services.ingestion.tarball import StreamingTarballProcessor
from app.services.parser.chunker import CodeChunker

logger = logging.getLogger(__name__)


class IngestionEngine:
    """Orchestrates streaming repository ingestion, semantic chunking, embedding, and atomic index promotion."""

    @classmethod
    async def run_indexing(
        cls,
        repository_id: uuid.UUID,
        branch_id: uuid.UUID,
        is_full_reindex: bool = False,
        job_id: uuid.UUID | None = None,
        session_factory: Any | None = None,
    ) -> uuid.UUID:
        """Executes full or incremental repository indexing."""
        session_maker = session_factory or AsyncSessionLocal
        async with session_maker() as session:
            # 1. Fetch Repository and Branch metadata
            repo = await session.get(
                Repository,
                repository_id,
                options=[selectinload(Repository.project)],
            )
            if not repo:
                raise NotFoundException("Repository", repository_id)

            branch = await session.get(RepositoryBranch, branch_id)
            if not branch:
                raise NotFoundException("RepositoryBranch", branch_id)

            # Find organization owner/admin user with GitHub installation ID
            from app.models.auth import Membership, User

            user_query = (
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == repo.project.organization_id,
                    User.github_installation_id.is_not(None),
                )
                .limit(1)
            )
            user_res = await session.execute(user_query)
            user = user_res.scalars().first()

            if not user or not user.github_installation_id:
                raise ForgeAIException(
                    "No GitHub installation found for organization.", status_code=400
                )

            installation_id = user.github_installation_id

            # Update Repository status to INDEXING
            repo.indexing_status = IndexingStatus.indexing
            await session.commit()

        # 2. Get ephemeral installation token (outside DB transaction)
        scoped_repo_ids = [repo.github_repo_id] if repo.github_repo_id else None
        token = await github_client.get_installation_access_token(
            installation_id, repository_ids=scoped_repo_ids
        )

        # 3. Fetch latest commit SHA for branch from GitHub
        owner, repo_name = repo.full_name.split("/", 1)
        branch_info = await github_client._request(
            "GET",
            f"/repos/{owner}/{repo_name}/branches/{branch.name}",
            token=token,
        )
        branch_data = branch_info.json() if callable(getattr(branch_info, "json", None)) else {}
        if hasattr(branch_data, "__await__"):
            branch_data = await branch_data
        commit_sha = (
            (branch_data.get("commit", {}).get("sha") if isinstance(branch_data, dict) else None)
            or branch.latest_commit_sha
            or "HEAD"
        )

        # 4. Create RepositoryIndexVersion (BUILDING) & IndexingJob in short DB transaction
        async with session_maker() as session:
            index_version = RepositoryIndexVersion(
                repository_id=repository_id,
                branch_id=branch_id,
                commit_sha=commit_sha,
                status=IndexVersionStatus.BUILDING,
            )
            session.add(index_version)
            await session.flush()
            index_version_id = index_version.id

            if job_id:
                job = await session.get(IndexingJob, job_id)
                if job:
                    job.index_version_id = index_version_id
                    job.commit_sha = commit_sha
                    job.status = IndexingJobStatus.ACQUIRING
                    job.started_at = datetime.datetime.now(datetime.UTC)
            else:
                job = IndexingJob(
                    repository_id=repository_id,
                    branch_id=branch_id,
                    index_version_id=index_version_id,
                    commit_sha=commit_sha,
                    status=IndexingJobStatus.ACQUIRING,
                    started_at=datetime.datetime.now(datetime.UTC),
                )
                session.add(job)
                await session.flush()
                job_id = job.id

            # Fetch active index version for diffing if not full re-index
            active_version_id: uuid.UUID | None = None
            existing_hashes: dict[str, str] = {}

            if not is_full_reindex:
                active_q = select(RepositoryIndexVersion).where(
                    RepositoryIndexVersion.branch_id == branch_id,
                    RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
                )
                active_res = await session.execute(active_q)
                active_ver = active_res.scalars().first()
                if active_ver:
                    active_version_id = active_ver.id
                    files_q = select(RepositoryFile).where(
                        RepositoryFile.index_version_id == active_version_id
                    )
                    files_res = await session.execute(files_q)
                    for f in files_res.scalars().all():
                        existing_hashes[f.file_path] = f.content_hash

            await session.commit()

        # 5. Stream and extract repository files from GitHub tarball (outside DB transaction)
        try:
            tarball_url = f"https://api.github.com/repos/{owner}/{repo_name}/tarball/{commit_sha}"
            incoming_entries = []
            async for file_entry in StreamingTarballProcessor.stream_and_extract_files(
                tarball_url, token
            ):
                incoming_entries.append(file_entry)

            # Calculate diff
            diff = IndexDiffer.calculate_diff(existing_hashes, incoming_entries)

            # 6. Parse AST and Semantic Chunking for added & modified files
            async with session_maker() as session:
                job = await session.get(IndexingJob, job_id)
                if job:
                    job.status = IndexingJobStatus.PARSING
                    job.total_files = len(incoming_entries)
                await session.commit()

            files_to_parse = diff.added_files + diff.modified_files
            parsed_results = []
            for file_entry in files_to_parse:
                parse_res = CodeChunker.parse_and_chunk_file(
                    file_entry.file_path, file_entry.content
                )
                parsed_results.append((file_entry, parse_res))

            # 7. Persist parsed draft chunks and copy unchanged files in short DB transaction
            chunks_to_embed_payload: list[tuple[uuid.UUID, str]] = []

            async with session_maker() as session:
                # A. Insert new/modified files, chunks, and dependencies
                for file_entry, parse_res in parsed_results:
                    _, ext = os.path.splitext(file_entry.file_path)
                    db_file = RepositoryFile(
                        index_version_id=index_version_id,
                        repository_id=repository_id,
                        file_path=file_entry.file_path,
                        file_name=os.path.basename(file_entry.file_path),
                        extension=ext.lower(),
                        language=parse_res.language,
                        size_bytes=file_entry.size_bytes,
                        content_hash=file_entry.content_hash,
                        is_binary=False,
                    )
                    session.add(db_file)
                    await session.flush()

                    for chunk in parse_res.chunks:
                        db_chunk = CodeChunk(
                            index_version_id=index_version_id,
                            file_id=db_file.id,
                            repository_id=repository_id,
                            chunk_index=chunk.chunk_index,
                            chunk_type=chunk.chunk_type,
                            symbol_name=chunk.symbol_name,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            content=chunk.content,
                            context_header=chunk.context_header,
                            token_count=chunk.token_count,
                        )
                        session.add(db_chunk)
                        await session.flush()
                        # Full text to embed = context_header + "\n" + content
                        text_to_embed = f"{chunk.context_header}\n{chunk.content}"
                        chunks_to_embed_payload.append((db_chunk.id, text_to_embed))

                    for dep in parse_res.dependencies:
                        db_dep = CodeDependency(
                            index_version_id=index_version_id,
                            file_id=db_file.id,
                            repository_id=repository_id,
                            source_symbol=dep.source_symbol,
                            target_symbol=dep.target_symbol,
                            imported_path=dep.imported_path,
                            dependency_type=dep.dependency_type,
                        )
                        session.add(db_dep)

                # B. Copy unchanged files and embeddings from active version
                if active_version_id and diff.unchanged_files:
                    unchanged_paths = {f.file_path for f in diff.unchanged_files}
                    old_files_q = (
                        select(RepositoryFile)
                        .where(
                            RepositoryFile.index_version_id == active_version_id,
                            RepositoryFile.file_path.in_(unchanged_paths),
                        )
                        .options(
                            selectinload(RepositoryFile.chunks).selectinload(CodeChunk.embeddings)
                        )
                    )
                    old_files_res = await session.execute(old_files_q)
                    old_files = old_files_res.scalars().all()

                    for old_f in old_files:
                        new_f = RepositoryFile(
                            index_version_id=index_version_id,
                            repository_id=repository_id,
                            file_path=old_f.file_path,
                            file_name=old_f.file_name,
                            extension=old_f.extension,
                            language=old_f.language,
                            size_bytes=old_f.size_bytes,
                            content_hash=old_f.content_hash,
                            is_binary=old_f.is_binary,
                        )
                        session.add(new_f)
                        await session.flush()

                        for old_c in old_f.chunks:
                            new_c = CodeChunk(
                                index_version_id=index_version_id,
                                file_id=new_f.id,
                                repository_id=repository_id,
                                chunk_index=old_c.chunk_index,
                                chunk_type=old_c.chunk_type,
                                symbol_name=old_c.symbol_name,
                                start_line=old_c.start_line,
                                end_line=old_c.end_line,
                                content=old_c.content,
                                context_header=old_c.context_header,
                                token_count=old_c.token_count,
                            )
                            session.add(new_c)
                            await session.flush()

                            for old_emb in old_c.embeddings:
                                new_emb = ChunkEmbedding(
                                    chunk_id=new_c.id,
                                    index_version_id=index_version_id,
                                    repository_id=repository_id,
                                    provider=old_emb.provider,
                                    model=old_emb.model,
                                    dimension=old_emb.dimension,
                                    embedding_version=old_emb.embedding_version,
                                    embedding=old_emb.embedding,
                                )
                                session.add(new_emb)

                # Update job progress
                total_chunks_q = select(CodeChunk).where(
                    CodeChunk.index_version_id == index_version_id
                )
                total_chunks_res = await session.execute(total_chunks_q)
                total_chunks_count = len(total_chunks_res.scalars().all())

                job = await session.get(IndexingJob, job_id)
                if job:
                    job.total_chunks = total_chunks_count
                    job.processed_files = len(incoming_entries)
                    job.status = IndexingJobStatus.EMBEDDING

                await session.commit()

            # 8. Generate Embeddings outside DB transaction in batches
            embed_provider = get_embedding_provider()
            generated_vectors: list[tuple[uuid.UUID, list[float]]] = []

            if chunks_to_embed_payload:
                chunk_ids = [c[0] for c in chunks_to_embed_payload]
                texts = [c[1] for c in chunks_to_embed_payload]
                vectors = await embed_provider.embed_documents(texts)

                for c_id, vec in zip(chunk_ids, vectors, strict=False):
                    generated_vectors.append((c_id, vec))

            # 9. Save vectors and promote index atomically in short DB transaction
            async with session_maker() as session:
                for chunk_id, vec in generated_vectors:
                    db_emb = ChunkEmbedding(
                        chunk_id=chunk_id,
                        index_version_id=index_version_id,
                        repository_id=repository_id,
                        provider=embed_provider.provider_name,
                        model=embed_provider.model_name,
                        dimension=embed_provider.dimension,
                        embedding_version=embed_provider.version,
                        embedding=vec,
                    )
                    session.add(db_emb)

                await session.flush()

                # Validate integrity
                chunks_count_q = select(CodeChunk).where(
                    CodeChunk.index_version_id == index_version_id
                )
                embeddings_count_q = select(ChunkEmbedding).where(
                    ChunkEmbedding.index_version_id == index_version_id
                )
                c_count = len((await session.execute(chunks_count_q)).scalars().all())
                e_count = len((await session.execute(embeddings_count_q)).scalars().all())

                if c_count != e_count:
                    raise ForgeAIException(
                        f"Index validation failed: chunks count ({c_count}) != embeddings count ({e_count})",
                        status_code=500,
                    )

                # 10. Atomic Index Promotion
                # A. Mark old ACTIVE versions for branch as SUPERSEDED
                await session.execute(
                    update(RepositoryIndexVersion)
                    .where(
                        RepositoryIndexVersion.branch_id == branch_id,
                        RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
                    )
                    .values(status=IndexVersionStatus.SUPERSEDED)
                )

                # B. Mark new version as ACTIVE
                new_version = await session.get(RepositoryIndexVersion, index_version_id)
                if new_version:
                    new_version.status = IndexVersionStatus.ACTIVE
                    new_version.total_files = len(incoming_entries)
                    new_version.total_chunks = c_count
                    new_version.completed_at = datetime.datetime.now(datetime.UTC)

                # C. Update Branch and Repository status
                branch_obj = await session.get(RepositoryBranch, branch_id)
                if branch_obj:
                    branch_obj.latest_commit_sha = commit_sha
                    branch_obj.indexed_at = datetime.datetime.now(datetime.UTC)

                repo_obj = await session.get(Repository, repository_id)
                if repo_obj:
                    repo_obj.indexing_status = IndexingStatus.ready

                # D. Update Job status
                job_obj = await session.get(IndexingJob, job_id)
                if job_obj:
                    job_obj.embedded_chunks = len(generated_vectors)
                    job_obj.status = IndexingJobStatus.COMPLETED
                    job_obj.completed_at = datetime.datetime.now(datetime.UTC)

                await session.commit()
                logger.info(
                    f"Successfully indexed repository {repo.full_name} ({branch.name}) at commit {commit_sha[:7]} -> {c_count} chunks"
                )

            return index_version_id

        except Exception as exc:
            logger.exception(f"Indexing failed for repository {repository_id}: {str(exc)}")
            # Fail gracefully: mark index version FAILED and preserve existing ACTIVE index
            async with session_maker() as session:
                if index_version_id:
                    ver = await session.get(RepositoryIndexVersion, index_version_id)
                    if ver:
                        ver.status = IndexVersionStatus.FAILED

                if job_id:
                    job_obj = await session.get(IndexingJob, job_id)
                    if job_obj:
                        job_obj.status = IndexingJobStatus.FAILED
                        from app.core.exceptions import EmbeddingQuotaExhaustedException
                        from app.services.embedding.gemini import sanitize_error

                        if isinstance(exc, EmbeddingQuotaExhaustedException):
                            job_obj.error_message = exc.message
                        elif "quota exhausted" in str(exc).lower() or "resource_exhausted" in str(exc).lower():
                            job_obj.error_message = (
                                "Gemini embedding quota exhausted. Indexing can resume when the provider quota resets or billing/quota is increased."
                            )
                        else:
                            job_obj.error_message = sanitize_error(str(exc))
                        job_obj.completed_at = datetime.datetime.now(datetime.UTC)

                repo_obj = await session.get(Repository, repository_id)
                if repo_obj:
                    # If we already have an active index, restore READY; otherwise FAILED
                    active_q = select(RepositoryIndexVersion).where(
                        RepositoryIndexVersion.branch_id == branch_id,
                        RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
                    )
                    active_ver = (await session.execute(active_q)).scalars().first()
                    repo_obj.indexing_status = (
                        IndexingStatus.ready if active_ver else IndexingStatus.failed
                    )

                await session.commit()

            raise exc
