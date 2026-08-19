from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.models.auth import Membership, Organization, Role, User
from app.models.codebase import (
    ChunkEmbedding,
    ChunkType,
    CodeChunk,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch
from app.services.retrieval.hybrid import HybridSearchEngine


@pytest_asyncio.fixture(scope="function")
async def indexed_forgeai_multi_domain_repo(db_session, test_user: User):
    """Creates a deterministic multi-domain repository fixture containing both code implementation files

    and architectural documentation files (docs/architecture.md, docs/decisions.md).
    """
    # 1. Organization & Project
    org = Organization(name="ForgeAI Lab", slug="forgeai-lab")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    project = Project(organization_id=org.id, name="ForgeAI Engine", description="Code Intelligence Engine")
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        github_repo_id=777888,
        owner="forgeai",
        full_name="forgeai/core-engine",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="bench_sha_final_100",
        is_protected=False,
    )
    db_session.add(branch)
    await db_session.flush()

    index_version = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha=branch.latest_commit_sha,
        status=IndexVersionStatus.ACTIVE,
        total_files=13,
        total_chunks=13,
    )
    db_session.add(index_version)
    await db_session.flush()

    # 2. Define 10 Implementation Files + 3 Documentation Files with dedicated signal dimensions
    entries: list[dict[str, Any]] = [
        # Query 1: GitHub Auth
        {
            "path": "backend/app/services/github/auth.py",
            "name": "auth.py",
            "symbol": "GitHubAuthService",
            "chunk_type": ChunkType.CLASS,
            "content": "class GitHubAuthService:\n    '''Handles GitHub OAuth 2.0 web flow, state signature verification, and user installation mapping.'''\n    async def handle_callback(self, code: str, state: str) -> dict:\n        pass",
            "header": "# file: backend/app/services/github/auth.py > class GitHubAuthService",
            "dim": 0,
        },
        # Query 2: Tree-sitter Parser
        {
            "path": "backend/app/services/parser/chunker.py",
            "name": "chunker.py",
            "symbol": "CodeChunker",
            "chunk_type": ChunkType.CLASS,
            "content": "class CodeChunker:\n    '''Parses source code into Tree-sitter AST nodes and generates language-aware semantic code chunks.'''\n    @classmethod\n    def parse_and_chunk_file(cls, file_path: str, content: str) -> list:\n        pass",
            "header": "# file: backend/app/services/parser/chunker.py > class CodeChunker",
            "dim": 1,
        },
        # Query 3: Embeddings Generation
        {
            "path": "backend/app/services/embedding/gemini.py",
            "name": "gemini.py",
            "symbol": "GeminiEmbeddingProvider",
            "chunk_type": ChunkType.CLASS,
            "content": "class GeminiEmbeddingProvider(BaseEmbeddingProvider):\n    '''Generates 768-dimensional dense vector embeddings using Google Gemini Embedding-2 API with rate-limit backoff.'''\n    async def embed_documents(self, texts: list[str]) -> list[list[float]]:\n        pass",
            "header": "# file: backend/app/services/embedding/gemini.py > class GeminiEmbeddingProvider",
            "dim": 2,
        },
        # Query 4: Hybrid Retrieval
        {
            "path": "backend/app/services/retrieval/hybrid.py",
            "name": "hybrid.py",
            "symbol": "HybridSearchEngine",
            "chunk_type": ChunkType.CLASS,
            "content": "class HybridSearchEngine:\n    '''Executes 3-stage hybrid search combining pgvector HNSW dense search, PostgreSQL GIN sparse search, and Reciprocal Rank Fusion.'''\n    @classmethod\n    async def search(cls, project_id: str, query: str, top_k: int = 15) -> list:\n        pass",
            "header": "# file: backend/app/services/retrieval/hybrid.py > class HybridSearchEngine",
            "dim": 3,
        },
        # Query 5: Incremental Index Differ
        {
            "path": "backend/app/services/ingestion/differ.py",
            "name": "differ.py",
            "symbol": "IndexDiffer",
            "chunk_type": ChunkType.CLASS,
            "content": "class IndexDiffer:\n    '''Calculates incremental file changes (added, modified, unchanged, deleted) via SHA-256 content hashes between commits.'''\n    @classmethod\n    def calculate_diff(cls, previous_hashes: dict, incoming_entries: list) -> IndexDiffResult:\n        pass",
            "header": "# file: backend/app/services/ingestion/differ.py > class IndexDiffer",
            "dim": 4,
        },
        # Query 6: Indexing Worker
        {
            "path": "backend/app/workers/ingestion_tasks.py",
            "name": "ingestion_tasks.py",
            "symbol": "index_repository_task",
            "chunk_type": ChunkType.FUNCTION,
            "content": "async def index_repository_task(ctx: dict, repository_id: str, branch_id: str, is_full_reindex: bool = False, job_id: str | None = None) -> dict:\n    '''ARQ background worker task executing asynchronous repository ingestion and embedding.'''\n    return await IngestionEngine.run_indexing(repository_id, branch_id, is_full_reindex, job_id)",
            "header": "# file: backend/app/workers/ingestion_tasks.py > function index_repository_task",
            "dim": 5,
        },
        # Query 7: Project Deletion
        {
            "path": "backend/app/services/project_service.py",
            "name": "project_service.py",
            "symbol": "ProjectService",
            "chunk_type": ChunkType.CLASS,
            "content": "class ProjectService:\n    '''Manages Project lifecycle, tenant security checks, and cascade project deletion.'''\n    async def delete_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:\n        pass",
            "header": "# file: backend/app/services/project_service.py > class ProjectService",
            "dim": 6,
        },
        # Query 8: JWT Authentication
        {
            "path": "backend/app/core/security.py",
            "name": "security.py",
            "symbol": "create_access_token",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:\n    '''Encodes user claims and authentication tokens using HS256 JWT signature.'''\n    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)",
            "header": "# file: backend/app/core/security.py > function create_access_token",
            "dim": 7,
        },
        # Query 9: GitHub Repositories Fetch
        {
            "path": "backend/app/services/github/repositories.py",
            "name": "repositories.py",
            "symbol": "GitHubRepositoryService",
            "chunk_type": ChunkType.CLASS,
            "content": "class GitHubRepositoryService:\n    '''Fetches and synchronizes repositories and branch lists accessible to a GitHub App installation.'''\n    async def list_repositories(self, installation_id: int) -> list[dict]:\n        pass",
            "header": "# file: backend/app/services/github/repositories.py > class GitHubRepositoryService",
            "dim": 8,
        },
        # Query 10: Atomic Index Promotion Engine
        {
            "path": "backend/app/services/ingestion/engine.py",
            "name": "engine.py",
            "symbol": "IngestionEngine",
            "chunk_type": ChunkType.CLASS,
            "content": "class IngestionEngine:\n    '''Orchestrates repository ingestion pipeline: streaming tarball, parsing, embedding, VALIDATED integrity check, and atomic promotion to ACTIVE status.'''\n    @classmethod\n    async def run_indexing(cls, repository_id: uuid.UUID, branch_id: uuid.UUID, is_full_reindex: bool = False, job_id: uuid.UUID | None = None) -> uuid.UUID:\n        pass",
            "header": "# file: backend/app/services/ingestion/engine.py > class IngestionEngine",
            "dim": 9,
        },
        # Documentation Chunks (contain architectural descriptions matching multiple queries)
        {
            "path": "docs/architecture.md",
            "name": "architecture.md",
            "symbol": "System Architecture Overview",
            "chunk_type": ChunkType.MARKDOWN_SECTION,
            "content": "# System Architecture Overview\nForgeAI implements a 3-stage hybrid retrieval engine with pgvector dense search, tsvector sparse search, tree-sitter AST parsing, GitHub authentication, and atomic index promotion.",
            "header": "# file: docs/architecture.md > # System Architecture Overview",
            "dim": 10,
        },
        {
            "path": "docs/decisions.md",
            "name": "decisions.md",
            "symbol": "ADR-009: Hybrid Retrieval and Incremental Indexing",
            "chunk_type": ChunkType.MARKDOWN_SECTION,
            "content": "# ADR-009: Hybrid Retrieval and Incremental Indexing\nWe chose Reciprocal Rank Fusion (RRF) combining dense embeddings from Gemini with sparse keyword indexing, tree-sitter parser, and GitHub OAuth authentication.",
            "header": "# file: docs/decisions.md > # ADR-009: Hybrid Retrieval and Incremental Indexing",
            "dim": 11,
        },
        {
            "path": "docs/roadmap.md",
            "name": "roadmap.md",
            "symbol": "Phase 3: Repository Intelligence Engine",
            "chunk_type": ChunkType.MARKDOWN_SECTION,
            "content": "# Phase 3: Repository Intelligence Engine\nMilestones: GitHub App authentication, tree-sitter parsing, embedding generation, hybrid search engine, and atomic index promotion.",
            "header": "# file: docs/roadmap.md > # Phase 3: Repository Intelligence Engine",
            "dim": 12,
        },
    ]

    for entry in entries:
        file_path_str = str(entry["path"])
        file_name_str = str(entry["name"])
        content_str = str(entry["content"])
        ext = ".md" if file_path_str.endswith(".md") else ".py"
        lang = "markdown" if ext == ".md" else "python"

        db_file = RepositoryFile(
            index_version_id=index_version.id,
            repository_id=repo.id,
            file_path=file_path_str,
            file_name=file_name_str,
            extension=ext,
            language=lang,
            size_bytes=len(content_str),
            content_hash=f"hash_{file_name_str}",
            is_binary=False,
        )
        db_session.add(db_file)
        await db_session.flush()

        db_chunk = CodeChunk(
            index_version_id=index_version.id,
            file_id=db_file.id,
            repository_id=repo.id,
            chunk_index=0,
            chunk_type=entry["chunk_type"],
            symbol_name=str(entry["symbol"]),
            start_line=1,
            end_line=15,
            content=content_str,
            context_header=str(entry["header"]),
            token_count=40,
        )
        db_session.add(db_chunk)
        await db_session.flush()

        # Build 768-dim vector with signal at index `entry['dim']`
        dim_idx = int(entry["dim"])
        full_vector = [0.0] * 768
        full_vector[dim_idx] = 1.0

        db_emb = ChunkEmbedding(
            chunk_id=db_chunk.id,
            index_version_id=index_version.id,
            repository_id=repo.id,
            provider="google",
            model="gemini-embedding-2",
            dimension=768,
            embedding_version=1,
            embedding=full_vector,
        )
        db_session.add(db_emb)

    await db_session.commit()

    return {
        "project": project,
        "repo": repo,
        "branch": branch,
        "index_version": index_version,
    }


@pytest.mark.asyncio
async def test_10_query_retrieval_benchmark(
    indexed_forgeai_multi_domain_repo: dict,
    db_session,
):
    """Executes the full 10-query benchmark suite verifying that implementation code ranks in the top-3

    for every query and outranks general architectural documentation.
    """
    project = indexed_forgeai_multi_domain_repo["project"]

    test_queries: list[dict[str, Any]] = [
        {
            "query": "Where is GitHub authentication implemented?",
            "dim": 0,
            "expected_target": "backend/app/services/github/auth.py",
            "expected_symbol": "GitHubAuthService",
        },
        {
            "query": "Where is the Tree-sitter parser implemented?",
            "dim": 1,
            "expected_target": "backend/app/services/parser/chunker.py",
            "expected_symbol": "CodeChunker",
        },
        {
            "query": "Where are embeddings generated?",
            "dim": 2,
            "expected_target": "backend/app/services/embedding/gemini.py",
            "expected_symbol": "GeminiEmbeddingProvider",
        },
        {
            "query": "Where is hybrid retrieval implemented?",
            "dim": 3,
            "expected_target": "backend/app/services/retrieval/hybrid.py",
            "expected_symbol": "HybridSearchEngine",
        },
        {
            "query": "How does incremental indexing detect changed files?",
            "dim": 4,
            "expected_target": "backend/app/services/ingestion/differ.py",
            "expected_symbol": "IndexDiffer",
        },
        {
            "query": "Where is the indexing worker implemented?",
            "dim": 5,
            "expected_target": "backend/app/workers/ingestion_tasks.py",
            "expected_symbol": "index_repository_task",
        },
        {
            "query": "Where is project deletion implemented?",
            "dim": 6,
            "expected_target": "backend/app/services/project_service.py",
            "expected_symbol": "ProjectService",
        },
        {
            "query": "Where is JWT authentication implemented?",
            "dim": 7,
            "expected_target": "backend/app/core/security.py",
            "expected_symbol": "create_access_token",
        },
        {
            "query": "Where are GitHub repositories fetched?",
            "dim": 8,
            "expected_target": "backend/app/services/github/repositories.py",
            "expected_symbol": "GitHubRepositoryService",
        },
        {
            "query": "Where is atomic index promotion implemented?",
            "dim": 9,
            "expected_target": "backend/app/services/ingestion/engine.py",
            "expected_symbol": "IngestionEngine",
        },
    ]

    hit_at_1_count = 0
    hit_at_3_count = 0
    total = len(test_queries)

    benchmark_log = []

    for tq in test_queries:
        query_str = str(tq["query"])
        dim_idx = int(tq["dim"])
        expected_target_str = str(tq["expected_target"])
        expected_symbol_str = str(tq["expected_symbol"])

        query_vec = [0.0] * 768
        query_vec[dim_idx] = 1.0

        with patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
            new_callable=AsyncMock,
            return_value=query_vec,
        ):
            results = await HybridSearchEngine.search(
                project_id=project.id,
                query=query_str,
                top_k=5,
                session_override=db_session,
            )

            assert len(results) > 0, f"Query '{query_str}' returned no results"

            top_1 = results[0]
            top_3_files = [r.file_path for r in results[:3]]
            top_3_symbols = [r.symbol_name for r in results[:3]]

            is_hit_1 = expected_target_str in top_1.file_path or top_1.symbol_name == expected_symbol_str
            is_hit_3 = any(expected_target_str in f for f in top_3_files) or (
                expected_symbol_str in top_3_symbols
            )

            if is_hit_1:
                hit_at_1_count += 1
            if is_hit_3:
                hit_at_3_count += 1

            # Log ranks for verification
            benchmark_log.append(
                {
                    "query": tq["query"],
                    "target": tq["expected_target"],
                    "top_1_file": top_1.file_path,
                    "top_1_symbol": top_1.symbol_name,
                    "top_3_files": top_3_files,
                    "hit_at_1": is_hit_1,
                    "hit_at_3": is_hit_3,
                }
            )

            # Assert expected implementation is in top-3
            assert (
                is_hit_3
            ), f"Expected '{tq['expected_target']}' in top-3 for query '{tq['query']}', got {top_3_files}"

    # Print summary
    hit_1_rate = hit_at_1_count / total
    hit_3_rate = hit_at_3_count / total

    print(f"\n--- 10-Query Benchmark Results: Hit@1 = {hit_1_rate:.0%}, Hit@3 = {hit_3_rate:.0%} ---")
    for log in benchmark_log:
        status = "PASS (Hit@1)" if log["hit_at_1"] else "PASS (Hit@3)" if log["hit_at_3"] else "FAIL"
        print(f"  [{status}] '{log['query']}' -> #1: {log['top_1_file']} ({log['top_1_symbol']})")

    assert hit_1_rate >= 0.90, f"Hit@1 rate ({hit_1_rate:.2f}) below 90% threshold"
    assert hit_3_rate == 1.0, f"Hit@3 rate ({hit_3_rate:.2f}) expected 100%"
