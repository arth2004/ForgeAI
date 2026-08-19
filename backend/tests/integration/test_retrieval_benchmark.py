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
async def benchmark_repo_fixture(db_session, test_user: User):
    """Creates a deterministic multi-component codebase fixture for retrieval quality benchmarking."""
    # 1. Organization & Project
    org = Organization(name="Benchmark Labs", slug="benchmark-labs")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    project = Project(organization_id=org.id, name="Benchmark Project", description="Retrieval Benchmark")
    db_session.add(project)
    await db_session.flush()

    # 2. Repository & Branch
    repo = Repository(
        project_id=project.id,
        github_repo_id=555444,
        owner="benchmark-labs",
        full_name="benchmark-labs/core-platform",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="bench_sha_123456",
        is_protected=False,
    )
    db_session.add(branch)
    await db_session.flush()

    # 3. Active Index Version
    index_version = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha=branch.latest_commit_sha,
        status=IndexVersionStatus.ACTIVE,
        total_files=5,
        total_chunks=5,
    )
    db_session.add(index_version)
    await db_session.flush()

    # 4. Five Distinct Domain Files & Code Chunks
    files_spec = [
        {
            "path": "app/services/auth_service.py",
            "name": "auth_service.py",
            "symbol": "verify_jwt_token",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def verify_jwt_token(token: str) -> dict:\n    '''Validates HS256 JWT signature and claims.'''\n    return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])",
            "header": "# file: app/services/auth_service.py > function verify_jwt_token",
            "vec_signal": [1.0, 0.0, 0.0, 0.0, 0.0],
        },
        {
            "path": "app/core/crypto_cipher.py",
            "name": "crypto_cipher.py",
            "symbol": "encrypt_secret_payload",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def encrypt_secret_payload(plaintext: str, key_hex: str) -> str:\n    '''Encrypts sensitive API credentials using AES-256-GCM cipher.'''\n    aesgcm = AESGCM(bytes.fromhex(key_hex))\n    return aesgcm.encrypt(nonce, plaintext.encode(), None).hex()",
            "header": "# file: app/core/crypto_cipher.py > function encrypt_secret_payload",
            "vec_signal": [0.0, 1.0, 0.0, 0.0, 0.0],
        },
        {
            "path": "app/services/differ.py",
            "name": "differ.py",
            "symbol": "calculate_sha256_diff",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def calculate_sha256_diff(stored_hashes: dict[str, str], incoming_entries: list) -> IndexDiffResult:\n    '''Computes added, modified, unchanged and deleted files via SHA-256 content hashes.'''\n    return IndexDiffResult(added, modified, unchanged, deleted)",
            "header": "# file: app/services/differ.py > function calculate_sha256_diff",
            "vec_signal": [0.0, 0.0, 1.0, 0.0, 0.0],
        },
        {
            "path": "app/services/hybrid_retrieval.py",
            "name": "hybrid_retrieval.py",
            "symbol": "reciprocal_rank_fusion",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def reciprocal_rank_fusion(dense_ranks: list, sparse_ranks: list, symbol_ranks: list, k: int = 60) -> list:\n    '''Fuses 3-stage ranking scores using reciprocal rank fusion formula.'''\n    score = sum(w / (k + rank) for w, rank in ranks)\n    return sorted_results",
            "header": "# file: app/services/hybrid_retrieval.py > function reciprocal_rank_fusion",
            "vec_signal": [0.0, 0.0, 0.0, 1.0, 0.0],
        },
        {
            "path": "app/api/endpoints/health.py",
            "name": "health.py",
            "symbol": "health_check_status",
            "chunk_type": ChunkType.FUNCTION,
            "content": "def health_check_status(db_conn: bool, redis_conn: bool) -> dict:\n    '''Returns overall platform health status for kubernetes readiness probes.'''\n    return {'status': 'healthy' if db_conn and redis_conn else 'degraded'}",
            "header": "# file: app/api/endpoints/health.py > function health_check_status",
            "vec_signal": [0.0, 0.0, 0.0, 0.0, 1.0],
        },
    ]

    created_chunks = {}
    for spec in files_spec:
        db_file = RepositoryFile(
            index_version_id=index_version.id,
            repository_id=repo.id,
            file_path=spec["path"],
            file_name=spec["name"],
            extension=".py",
            language="python",
            size_bytes=len(spec["content"]),
            content_hash=f"hash_{spec['symbol']}",
            is_binary=False,
        )
        db_session.add(db_file)
        await db_session.flush()

        db_chunk = CodeChunk(
            index_version_id=index_version.id,
            file_id=db_file.id,
            repository_id=repo.id,
            chunk_index=0,
            chunk_type=spec["chunk_type"],
            symbol_name=spec["symbol"],
            start_line=1,
            end_line=10,
            content=spec["content"],
            context_header=spec["header"],
            token_count=30,
        )
        db_session.add(db_chunk)
        await db_session.flush()

        # Build 768-dim vector padded with zeros
        full_vector = spec["vec_signal"] + [0.0] * (768 - len(spec["vec_signal"]))

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
        created_chunks[spec["symbol"]] = db_chunk

    await db_session.commit()

    return {
        "project": project,
        "repo": repo,
        "branch": branch,
        "index_version": index_version,
        "chunks": created_chunks,
    }


@pytest.mark.asyncio
async def test_retrieval_quality_benchmark_recall_and_hit_at_k(
    benchmark_repo_fixture: dict,
    db_session,
):
    """Deterministic retrieval quality benchmark verifying Hit@1, Recall@3, and exact symbol ranking across distinct concepts."""
    project = benchmark_repo_fixture["project"]

    # Test cases: (query, query_vector_signal, expected_symbol, expected_file)
    benchmark_queries = [
        {
            "query": "Where is verify_jwt_token implemented for JWT authentication?",
            "vec_signal": [1.0, 0.0, 0.0, 0.0, 0.0],
            "expected_symbol": "verify_jwt_token",
            "expected_file": "app/services/auth_service.py",
        },
        {
            "query": "AES-256-GCM cipher encryption for sensitive secret payloads",
            "vec_signal": [0.0, 1.0, 0.0, 0.0, 0.0],
            "expected_symbol": "encrypt_secret_payload",
            "expected_file": "app/core/crypto_cipher.py",
        },
        {
            "query": "How is SHA-256 content diff calculated for changed files?",
            "vec_signal": [0.0, 0.0, 1.0, 0.0, 0.0],
            "expected_symbol": "calculate_sha256_diff",
            "expected_file": "app/services/differ.py",
        },
        {
            "query": "Reciprocal rank fusion algorithm implementation",
            "vec_signal": [0.0, 0.0, 0.0, 1.0, 0.0],
            "expected_symbol": "reciprocal_rank_fusion",
            "expected_file": "app/services/hybrid_retrieval.py",
        },
        {
            "query": "Health check status readiness probe endpoint",
            "vec_signal": [0.0, 0.0, 0.0, 0.0, 1.0],
            "expected_symbol": "health_check_status",
            "expected_file": "app/api/endpoints/health.py",
        },
    ]

    hit_at_1_count = 0
    hit_at_3_count = 0
    total_queries = len(benchmark_queries)

    for item in benchmark_queries:
        query_vec = item["vec_signal"] + [0.0] * (768 - len(item["vec_signal"]))

        with patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
            new_callable=AsyncMock,
            return_value=query_vec,
        ):
            results = await HybridSearchEngine.search(
                project_id=project.id,
                query=item["query"],
                top_k=5,
                session_override=db_session,
            )

            assert len(results) > 0, f"Query '{item['query']}' returned no results"

            # Check top 1
            top_1 = results[0]
            if top_1.symbol_name == item["expected_symbol"]:
                hit_at_1_count += 1

            # Check top 3
            top_3_symbols = [r.symbol_name for r in results[:3]]
            top_3_files = [r.file_path for r in results[:3]]
            if item["expected_symbol"] in top_3_symbols and item["expected_file"] in top_3_files:
                hit_at_3_count += 1

            # Assert expected symbol appears within top 3
            assert (
                item["expected_symbol"] in top_3_symbols
            ), f"Expected '{item['expected_symbol']}' in top 3 for query '{item['query']}', got {top_3_symbols}"

    # Calculate and assert benchmark metrics
    hit_at_1_rate = hit_at_1_count / total_queries
    hit_at_3_rate = hit_at_3_count / total_queries

    assert hit_at_1_rate >= 0.8, f"Hit@1 rate ({hit_at_1_rate:.2f}) below 0.80 threshold"
    assert hit_at_3_rate == 1.0, f"Hit@3 rate ({hit_at_3_rate:.2f}) expected 1.00 (100%)"
