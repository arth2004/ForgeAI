import logging
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.codebase import (
    ChunkEmbedding,
    CodeChunk,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import Repository, RepositoryBranch
from app.services.embedding.factory import get_embedding_provider

logger = logging.getLogger(__name__)


def python_cosine_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine distance (1 - cosine similarity) in pure Python."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 1.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a, b in zip(vec_a, vec_b, strict=False)))
    norm_b = math.sqrt(sum(b * b for a, b in zip(vec_a, vec_b, strict=False)))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    sim = dot / (norm_a * norm_b)
    return 1.0 - max(-1.0, min(1.0, sim))


@dataclass
class RetrievedEvidenceChunk:
    chunk_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    chunk_type: str
    context_header: str
    content: str
    rrf_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    symbol_rank: int | None = None
    commit_sha: str = ""
    branch_name: str = ""
    index_version_id: uuid.UUID | None = None
    repository_id: uuid.UUID | None = None


class HybridSearchEngine:
    """3-Stage Hybrid Retrieval Engine combining pgvector HNSW, PostgreSQL tsvector, and Reciprocal Rank Fusion."""

    @classmethod
    async def search(
        cls,
        project_id: uuid.UUID,
        query: str,
        branch_id: uuid.UUID | None = None,
        top_k: int = 15,
        dense_weight: float = 1.0,
        sparse_weight: float = 0.8,
        symbol_weight: float = 1.2,
        rrf_k: int = 60,
        session_override: AsyncSession | None = None,
    ) -> list[RetrievedEvidenceChunk]:
        """Executes hybrid retrieval across active repository indexes for a project."""
        if not query.strip():
            return []

        async def _execute_search(session: AsyncSession) -> list[RetrievedEvidenceChunk]:
            # 1. Resolve active index versions for the project (and optionally branch)
            index_versions_q = (
                select(RepositoryIndexVersion)
                .join(Repository, Repository.id == RepositoryIndexVersion.repository_id)
                .join(RepositoryBranch, RepositoryBranch.id == RepositoryIndexVersion.branch_id)
                .where(
                    Repository.project_id == project_id,
                    RepositoryIndexVersion.status == IndexVersionStatus.ACTIVE,
                )
                .options(
                    selectinload(RepositoryIndexVersion.repository),
                    selectinload(RepositoryIndexVersion.branch),
                )
            )

            if branch_id:
                index_versions_q = index_versions_q.where(
                    RepositoryIndexVersion.branch_id == branch_id
                )

            index_versions_res = await session.execute(index_versions_q)
            active_versions = index_versions_res.scalars().all()

            if not active_versions:
                return []

            active_version_ids = [v.id for v in active_versions]
            version_map = {v.id: v for v in active_versions}

            # 2. Stage 1: Dense Vector Similarity Search
            embed_provider = get_embedding_provider()
            query_vector = await embed_provider.embed_query(query)

            dense_ranks: dict[uuid.UUID, int] = {}
            is_sqlite = session.bind and session.bind.dialect.name == "sqlite"

            if is_sqlite:
                # SQLite fallback: fetch vector embeddings and calculate cosine distance in Python
                embs_q = select(ChunkEmbedding).where(
                    ChunkEmbedding.index_version_id.in_(active_version_ids)
                )
                embs_res = await session.execute(embs_q)
                embs = embs_res.scalars().all()
                scored_embs = [
                    (e.chunk_id, python_cosine_distance(query_vector, e.embedding)) for e in embs
                ]
                scored_embs.sort(key=lambda x: x[1])
                for rank_idx, (cid, _) in enumerate(scored_embs[:50]):
                    dense_ranks[cid] = rank_idx + 1
            else:
                # PostgreSQL pgvector HNSW cosine distance
                dense_stmt = (
                    select(
                        ChunkEmbedding.chunk_id,
                        ChunkEmbedding.embedding.cosine_distance(query_vector).label("distance"),
                    )
                    .where(ChunkEmbedding.index_version_id.in_(active_version_ids))
                    .order_by("distance")
                    .limit(50)
                )
                dense_res = await session.execute(dense_stmt)
                for rank_idx, row in enumerate(dense_res.all()):
                    dense_ranks[row.chunk_id] = rank_idx + 1

            # 3. Stage 2: Sparse Full-Text Search via PostgreSQL ts_rank_cd on GIN tsvector
            sparse_ranks: dict[uuid.UUID, int] = {}
            if is_sqlite:
                # SQLite fallback: keyword containment match
                terms = [w.lower() for w in query.split() if len(w) > 1]
                if terms:
                    chunks_q = select(CodeChunk).where(
                        CodeChunk.index_version_id.in_(active_version_ids)
                    )
                    chunks_all = (await session.execute(chunks_q)).scalars().all()
                    matches = []
                    for c in chunks_all:
                        text_body = f"{c.symbol_name or ''} {c.context_header} {c.content}".lower()
                        score = sum(1 for t in terms if t in text_body)
                        if score > 0:
                            matches.append((c.id, score))
                    matches.sort(key=lambda x: x[1], reverse=True)
                    for rank_idx, (cid, _) in enumerate(matches[:50]):
                        sparse_ranks[cid] = rank_idx + 1
            else:
                try:
                    sparse_stmt = (
                        select(
                            CodeChunk.id,
                            func.ts_rank_cd(
                                CodeChunk.search_vector,
                                func.plainto_tsquery("english", query),
                            ).label("rank"),
                        )
                        .where(
                            CodeChunk.index_version_id.in_(active_version_ids),
                            CodeChunk.search_vector.op("@@")(
                                func.plainto_tsquery("english", query)
                            ),
                        )
                        .order_by(desc("rank"))
                        .limit(50)
                    )
                    sparse_res = await session.execute(sparse_stmt)
                    for rank_idx, row in enumerate(sparse_res.all()):
                        sparse_ranks[row.id] = rank_idx + 1
                except Exception as e:
                    logger.warning(f"Full-text search fallback: {e}")

            # 4. Stage 3: Exact Path & Symbol Match Filtering
            symbol_ranks: dict[uuid.UUID, int] = {}
            terms = [t for t in query.split() if len(t) > 2]
            if terms:
                symbol_filters = []
                for t in terms:
                    symbol_filters.append(CodeChunk.symbol_name.ilike(f"%{t}%"))
                    symbol_filters.append(RepositoryFile.file_path.ilike(f"%{t}%"))

                symbol_stmt = (
                    select(CodeChunk.id)
                    .join(RepositoryFile, RepositoryFile.id == CodeChunk.file_id)
                    .where(
                        CodeChunk.index_version_id.in_(active_version_ids),
                        or_(*symbol_filters),
                    )
                    .limit(30)
                )
                symbol_res = await session.execute(symbol_stmt)
                for rank_idx, row in enumerate(symbol_res.all()):
                    symbol_ranks[row.id] = rank_idx + 1

            # 5. Stage 4: Reciprocal Rank Fusion (RRF)
            all_chunk_ids = (
                set(dense_ranks.keys()) | set(sparse_ranks.keys()) | set(symbol_ranks.keys())
            )
            if not all_chunk_ids:
                return []

            rrf_scores: dict[uuid.UUID, float] = {}
            for chunk_id in all_chunk_ids:
                score = 0.0
                if chunk_id in dense_ranks:
                    score += dense_weight / (rrf_k + dense_ranks[chunk_id])
                if chunk_id in sparse_ranks:
                    score += sparse_weight / (rrf_k + sparse_ranks[chunk_id])
                if chunk_id in symbol_ranks:
                    score += symbol_weight / (rrf_k + symbol_ranks[chunk_id])
                rrf_scores[chunk_id] = score

            # Sort top chunk IDs by RRF score descending
            sorted_chunk_ids = sorted(all_chunk_ids, key=lambda cid: rrf_scores[cid], reverse=True)[
                :top_k
            ]

            # 6. Retrieve detailed Chunk records with file and commit lineage
            chunks_stmt = (
                select(CodeChunk)
                .where(CodeChunk.id.in_(sorted_chunk_ids))
                .options(
                    selectinload(CodeChunk.file),
                    selectinload(CodeChunk.index_version).selectinload(
                        RepositoryIndexVersion.branch
                    ),
                )
            )
            chunks_res = await session.execute(chunks_stmt)
            chunk_records = {c.id: c for c in chunks_res.scalars().all()}

            results: list[RetrievedEvidenceChunk] = []
            for cid in sorted_chunk_ids:
                c = chunk_records.get(cid)
                if not c:
                    continue

                ver = version_map.get(c.index_version_id)
                commit_sha = ver.commit_sha if ver else ""
                branch_name = ver.branch.name if ver and ver.branch else ""

                results.append(
                    RetrievedEvidenceChunk(
                        chunk_id=c.id,
                        file_path=c.file.file_path if c.file else "",
                        start_line=c.start_line,
                        end_line=c.end_line,
                        symbol_name=c.symbol_name,
                        chunk_type=c.chunk_type.value
                        if hasattr(c.chunk_type, "value")
                        else str(c.chunk_type),
                        context_header=c.context_header,
                        content=c.content,
                        rrf_score=rrf_scores[cid],
                        dense_rank=dense_ranks.get(cid),
                        sparse_rank=sparse_ranks.get(cid),
                        symbol_rank=symbol_ranks.get(cid),
                        commit_sha=commit_sha,
                        branch_name=branch_name,
                        index_version_id=c.index_version_id,
                        repository_id=c.repository_id,
                    )
                )

            return results

        if session_override:
            return await _execute_search(session_override)
        else:
            async with AsyncSessionLocal() as session:
                return await _execute_search(session)
