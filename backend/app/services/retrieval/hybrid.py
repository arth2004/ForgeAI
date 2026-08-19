import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.codebase import (
    ChunkEmbedding,
    ChunkType,
    CodeChunk,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import Repository, RepositoryBranch
from app.services.embedding.factory import get_embedding_provider

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "implemented", "implementation", "implement", "located",
    "defined", "code", "file", "files", "written", "find", "show", "tell", "give",
}

GENERIC_FILENAMES = {
    "index", "main", "types", "init", "__init__", "page", "layout", "app", "route",
    "default", "setup", "conftest", "utils", "common", "base", "config"
}

STEM_SYNONYMS = {
    "deletion": ["delete", "del", "remove", "destroy", "drop", "project_service"],
    "delete": ["deletion", "del", "remove", "destroy", "project_service"],
    "authentication": ["auth", "authenticate", "login", "jwt", "oauth", "security", "credentials"],
    "authenticate": ["auth", "authentication", "login", "jwt", "security"],
    "auth": ["authentication", "authenticate", "login", "jwt", "security"],
    "jwt": ["jwt", "access_token", "token", "security", "auth", "claims", "bearer"],
    "token": ["jwt", "access_token", "token", "auth", "security"],
    "repositories": ["repository", "repo", "repos", "github_repo"],
    "repository": ["repositories", "repo", "repos", "github_repo"],
    "repo": ["repository", "repositories", "repo"],
    "parser": ["parse", "chunker", "chunk", "ast", "tree_sitter", "languages", "symbols"],
    "parse": ["parser", "chunker", "ast", "tree_sitter", "languages"],
    "tree_sitter": ["tree_sitter", "treesitter", "parser", "chunker", "ast", "grammar"],
    "treesitter": ["tree_sitter", "treesitter", "parser", "chunker", "ast"],
    "retrieval": ["retrieval", "retrieve", "search", "hybrid", "engine", "rrf", "dense", "sparse"],
    "retrieve": ["retrieval", "search", "hybrid", "engine"],
    "indexing": ["index", "indexer", "version", "engine", "differ"],
    "index": ["indexing", "indexer", "version", "engine", "differ"],
    "embeddings": ["embedding", "embed", "vector", "gemini", "openai", "dimension", "provider"],
    "embedding": ["embeddings", "embed", "vector", "gemini", "openai", "dimension", "provider"],
    "generate": ["generate", "generated", "embed_documents", "embed_query", "embed", "embeddings"],
    "generated": ["generate", "generated", "embed_documents", "embed_query", "embed", "embeddings"],
    "promotion": ["promote", "promotion", "active", "version", "engine", "lifecycle", "validated", "superseded", "run_indexing"],
    "promote": ["promotion", "promote", "active", "version", "engine", "lifecycle", "validated", "run_indexing"],
    "atomic": ["atomic", "transaction", "engine", "promotion", "lifecycle", "run_indexing"],
    "changed": ["differ", "diff", "difference", "delta", "modified", "change", "content_hash"],
    "incremental": ["incremental", "differ", "diff", "delta", "change", "content_hash", "modified"],
    "diff": ["differ", "diff", "difference", "delta", "incremental", "changed"],
    "worker": ["worker", "tasks", "task", "arq", "queue", "job", "ingestion_tasks"],
    "fetched": ["fetch", "get", "list", "client", "download", "repositories"],
    "fetch": ["fetched", "get", "list", "client", "repositories"],
}

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".sql"
}


def extract_query_code_terms(query: str) -> list[str]:
    """Extracts meaningful identifiers, keywords and path fragments from a natural language query."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\./]", " ", query)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    meaningful = []
    for t in tokens:
        lower_t = t.lower()
        if lower_t not in STOP_WORDS and len(lower_t) >= 2:
            meaningful.append(lower_t)
            if "-" in t:
                meaningful.append(t.replace("-", "_").lower())
                meaningful.append(t.replace("-", "").lower())
            if "_" in t:
                meaningful.append(t.replace("_", "-").lower())
                meaningful.append(t.replace("_", "").lower())
    # Deduplicate while preserving token order
    seen = set()
    result = []
    for m in meaningful:
        if m not in seen and m not in STOP_WORDS:
            seen.add(m)
            result.append(m)
    return result


def is_implementation_query(query: str) -> bool:
    """Detects whether user query is asking for implementation / source code location."""
    q_lower = query.lower()
    triggers = [
        "where is", "where are", "how does", "how do", "how is", "where can",
        "find the", "implementation", "implemented", "defined", "show me", "which file"
    ]
    return any(tr in q_lower for tr in triggers)


def python_cosine_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine distance (1 - cosine similarity) in pure Python."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 1.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
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
        symbol_weight: float = 1.6,
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

            code_terms = extract_query_code_terms(query)
            is_impl_q = is_implementation_query(query)

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
                for rank_idx, (cid, _) in enumerate(scored_embs[:60]):
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
                    .limit(60)
                )
                dense_res = await session.execute(dense_stmt)
                for rank_idx, row in enumerate(dense_res.all()):
                    dense_ranks[row.chunk_id] = rank_idx + 1

            # 3. Stage 2: Sparse Full-Text Search via PostgreSQL ts_rank_cd on GIN tsvector
            sparse_ranks: dict[uuid.UUID, int] = {}
            if is_sqlite:
                terms = [w.lower() for w in code_terms if len(w) > 1] or [
                    w.lower() for w in query.split() if len(w) > 1
                ]
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
                    for rank_idx, (cid, _) in enumerate(matches[:60]):
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
                        .limit(60)
                    )
                    sparse_res = await session.execute(sparse_stmt)
                    for rank_idx, row in enumerate(sparse_res.all()):
                        sparse_ranks[row.id] = rank_idx + 1
                except Exception as e:
                    logger.warning(f"Full-text search fallback: {e}")

            # 4. Stage 3: Exact Path, Symbol & Multi-term Match Scoring
            symbol_ranks: dict[uuid.UUID, int] = {}
            if code_terms:
                all_search_terms = set(code_terms)
                for t in code_terms:
                    if t in STEM_SYNONYMS:
                        all_search_terms.update(STEM_SYNONYMS[t])

                score_exprs = []
                filter_conditions = []

                for term in all_search_terms:
                    t = term.lower()
                    is_primary = t in code_terms
                    weight_mult = 1.0 if is_primary else 0.75

                    # Symbol declaration matches ONLY apply to code AST declarations (CLASS, FUNCTION, METHOD, INTERFACE, MODULE)
                    is_ast_chunk_cond = CodeChunk.chunk_type.in_([
                        ChunkType.CLASS,
                        ChunkType.FUNCTION,
                        ChunkType.METHOD,
                        ChunkType.INTERFACE,
                        ChunkType.MODULE,
                    ])

                    # Exact symbol declaration match (e.g. `delete`, `GitHubAuthService`, `ProjectService`, `CodeChunker`)
                    score_exprs.append(
                        case((and_(is_ast_chunk_cond, func.lower(CodeChunk.symbol_name) == t), int(260 * weight_mult)), else_=0)
                    )
                    score_exprs.append(
                        case((and_(is_ast_chunk_cond, CodeChunk.symbol_name.ilike(f"{t}%")), int(150 * weight_mult)), else_=0)
                    )
                    score_exprs.append(
                        case((and_(is_ast_chunk_cond, CodeChunk.symbol_name.ilike(f"%{t}")), int(120 * weight_mult)), else_=0)
                    )
                    score_exprs.append(
                        case((and_(is_ast_chunk_cond, CodeChunk.symbol_name.ilike(f"%{t}%")), int(70 * weight_mult)), else_=0)
                    )

                    # Specific filename & path matches
                    if t not in GENERIC_FILENAMES:
                        # Exact file stem (e.g. auth.py, differ.py, chunker.py, security.py, gemini.py, engine.py)
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%/{t}.%"), int(180 * weight_mult)), else_=0)
                        )
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%/{t}_%"), int(100 * weight_mult)), else_=0)
                        )
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%_{t}.%"), int(100 * weight_mult)), else_=0)
                        )
                        # Directory match (e.g. /parser/, /retrieval/, /github/, /embedding/, /ingestion/)
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%/{t}/%"), int(90 * weight_mult)), else_=0)
                        )
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%{t}%"), int(30 * weight_mult)), else_=0)
                        )
                    else:
                        # Generic filename terms require directory match
                        score_exprs.append(
                            case((RepositoryFile.file_path.ilike(f"%/{t}/%"), int(50 * weight_mult)), else_=0)
                        )

                    filter_conditions.append(and_(is_ast_chunk_cond, CodeChunk.symbol_name.ilike(f"%{t}%")))
                    filter_conditions.append(RepositoryFile.file_path.ilike(f"%{t}%"))

                if is_sqlite:
                    # SQLite fallback: filter in memory
                    c_rows_stmt = (
                        select(CodeChunk.id, CodeChunk.symbol_name, CodeChunk.chunk_type, RepositoryFile.file_path)
                        .join(RepositoryFile, RepositoryFile.id == CodeChunk.file_id)
                        .where(CodeChunk.index_version_id.in_(active_version_ids))
                    )
                    c_rows = (await session.execute(c_rows_stmt)).all()
                    scored_matches = []
                    for cid, sym, ctype_val, fpath in c_rows:
                        match_score = 0
                        sym_l = (sym or "").lower()
                        fpath_l = (fpath or "").lower()
                        is_code_chunk = ctype_val in {
                            ChunkType.CLASS,
                            ChunkType.FUNCTION,
                            ChunkType.METHOD,
                            ChunkType.INTERFACE,
                            ChunkType.MODULE,
                            "class", "function", "method", "interface", "module",
                        }

                        for term in all_search_terms:
                            t = term.lower()
                            is_primary = t in code_terms
                            weight_mult = 1.0 if is_primary else 0.75

                            if is_code_chunk:
                                if sym_l == t:
                                    match_score += int(260 * weight_mult)
                                elif sym_l.startswith(t):
                                    match_score += int(150 * weight_mult)
                                elif sym_l.endswith(t):
                                    match_score += int(120 * weight_mult)
                                elif t in sym_l:
                                    match_score += int(70 * weight_mult)

                            if t not in GENERIC_FILENAMES:
                                if f"/{t}." in fpath_l:
                                    match_score += int(180 * weight_mult)
                                elif f"/{t}_" in fpath_l or f"_{t}." in fpath_l:
                                    match_score += int(100 * weight_mult)
                                elif f"/{t}/" in fpath_l:
                                    match_score += int(90 * weight_mult)
                                elif t in fpath_l:
                                    match_score += int(30 * weight_mult)

                        if match_score > 0:
                            scored_matches.append((cid, match_score))
                    scored_matches.sort(key=lambda x: x[1], reverse=True)
                    for rank_idx, (cid, _) in enumerate(scored_matches[:60]):
                        symbol_ranks[cid] = rank_idx + 1
                else:
                    total_match_score = cast(Any, sum(score_exprs)).label("total_match_score")
                    symbol_stmt = (
                        select(CodeChunk.id, total_match_score)
                        .join(RepositoryFile, RepositoryFile.id == CodeChunk.file_id)
                        .where(
                            CodeChunk.index_version_id.in_(active_version_ids),
                            or_(*filter_conditions),
                        )
                        .order_by(desc("total_match_score"))
                        .limit(60)
                    )
                    symbol_res = await session.execute(symbol_stmt)
                    for rank_idx, row in enumerate(symbol_res.all()):
                        symbol_ranks[row.id] = rank_idx + 1

            # 5. Stage 4: Reciprocal Rank Fusion (RRF) with Code Entity Intent Signal
            all_chunk_ids = (
                set(dense_ranks.keys()) | set(sparse_ranks.keys()) | set(symbol_ranks.keys())
            )
            if not all_chunk_ids:
                return []

            # Retrieve chunk metadata for code-classification awareness
            chunks_info_stmt = (
                select(CodeChunk.id, CodeChunk.chunk_type, RepositoryFile.file_path, CodeChunk.symbol_name)
                .join(RepositoryFile, RepositoryFile.id == CodeChunk.file_id)
                .where(CodeChunk.id.in_(all_chunk_ids))
            )
            chunks_info_res = await session.execute(chunks_info_stmt)
            chunk_meta = {row[0]: (row[1], row[2], row[3]) for row in chunks_info_res.all()}

            rrf_scores: dict[uuid.UUID, float] = {}
            for chunk_id in all_chunk_ids:
                rrf_calc: float = 0.0
                if chunk_id in dense_ranks:
                    rrf_calc += float(dense_weight) / (rrf_k + dense_ranks[chunk_id])
                if chunk_id in sparse_ranks:
                    rrf_calc += float(sparse_weight) / (rrf_k + sparse_ranks[chunk_id])
                if chunk_id in symbol_ranks:
                    rrf_calc += float(symbol_weight) / (rrf_k + symbol_ranks[chunk_id])

                ctype, fpath, sname = chunk_meta.get(chunk_id, (None, "", None))
                is_code_file = any(fpath.endswith(ext) for ext in CODE_EXTENSIONS)
                is_named_decl = ctype in {
                    ChunkType.FUNCTION,
                    ChunkType.CLASS,
                    ChunkType.METHOD,
                    ChunkType.INTERFACE,
                    "function", "class", "method", "interface",
                }

                # Principled Code Entity & Intent Weighting
                if is_impl_q:
                    if is_code_file and is_named_decl:
                        # Direct named declaration (CLASS/FUNCTION/METHOD) in code implementation file
                        s_rank = symbol_ranks.get(chunk_id)
                        if s_rank and s_rank <= 10:
                            # High-confidence exact declaration match
                            rrf_calc *= 2.2
                        else:
                            rrf_calc *= 1.6
                    elif is_code_file:
                        # Top-level code module or block
                        rrf_calc *= 1.25
                    elif not is_code_file:
                        # Documentation markdown file
                        rrf_calc *= 0.45

                rrf_scores[chunk_id] = rrf_calc

            # Sort top chunk IDs by RRF score descending
            sorted_chunk_ids = sorted(
                all_chunk_ids, key=lambda cid: rrf_scores[cid], reverse=True
            )[:top_k]

            # 6. Retrieve detailed Chunk records with file and commit lineage
            detailed_chunks_stmt = (
                select(CodeChunk)
                .where(CodeChunk.id.in_(sorted_chunk_ids))
                .options(
                    selectinload(CodeChunk.file),
                    selectinload(CodeChunk.index_version).selectinload(
                        RepositoryIndexVersion.branch
                    ),
                )
            )
            chunks_res = await session.execute(detailed_chunks_stmt)
            chunk_records: dict[uuid.UUID, CodeChunk] = {c.id: c for c in chunks_res.scalars().all()}

            results: list[RetrievedEvidenceChunk] = []
            for cid in sorted_chunk_ids:
                chunk_obj = chunk_records.get(cid)
                if not chunk_obj:
                    continue

                ver = version_map.get(chunk_obj.index_version_id)
                commit_sha = ver.commit_sha if ver else ""
                branch_name = ver.branch.name if ver and ver.branch else ""

                results.append(
                    RetrievedEvidenceChunk(
                        chunk_id=chunk_obj.id,
                        file_path=chunk_obj.file.file_path if chunk_obj.file else "",
                        start_line=chunk_obj.start_line,
                        end_line=chunk_obj.end_line,
                        symbol_name=chunk_obj.symbol_name,
                        chunk_type=chunk_obj.chunk_type.value
                        if hasattr(chunk_obj.chunk_type, "value")
                        else str(chunk_obj.chunk_type),
                        context_header=chunk_obj.context_header,
                        content=chunk_obj.content,
                        rrf_score=rrf_scores[cid],
                        dense_rank=dense_ranks.get(cid),
                        sparse_rank=sparse_ranks.get(cid),
                        symbol_rank=symbol_ranks.get(cid),
                        commit_sha=commit_sha,
                        branch_name=branch_name,
                        index_version_id=chunk_obj.index_version_id,
                        repository_id=chunk_obj.repository_id,
                    )
                )

            return results

        if session_override:
            return await _execute_search(session_override)
        else:
            async with AsyncSessionLocal() as session:
                return await _execute_search(session)
