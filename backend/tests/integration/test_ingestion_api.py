import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.auth import User
from app.models.codebase import (
    ChunkEmbedding,
    ChunkType,
    CodeChunk,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch


@pytest_asyncio.fixture(scope="function")
async def seeded_project_and_index(db_session, test_user: User):
    # 1. Create Org & Project
    from app.models.auth import Membership, Organization, Role

    org = Organization(name="AI Lab", slug="ai-lab-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    test_user.github_installation_id = 776655
    db_session.add(test_user)

    project = Project(
        organization_id=org.id,
        name="AI Workspace",
        description="Test Workspace",
    )
    db_session.add(project)
    await db_session.flush()

    # 2. Create Repository & Branch
    repo = Repository(
        project_id=project.id,
        github_repo_id=987654,
        owner="ai-lab",
        full_name="ai-lab/ai-workspace",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="c0ffee1234567890abcdef1234567890abcdef12",
        is_protected=False,
    )
    db_session.add(branch)
    await db_session.flush()

    # 3. Create Active Index Version
    index_version = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha=branch.latest_commit_sha,
        status=IndexVersionStatus.ACTIVE,
        total_files=1,
        total_chunks=2,
    )
    db_session.add(index_version)
    await db_session.flush()

    # 4. Create File, Chunks, and Embeddings
    file_obj = RepositoryFile(
        index_version_id=index_version.id,
        repository_id=repo.id,
        file_path="src/security/encryption.py",
        file_name="encryption.py",
        extension=".py",
        language="python",
        size_bytes=500,
        content_hash="hash_enc_v1",
        is_binary=False,
    )
    db_session.add(file_obj)
    await db_session.flush()

    chunk1 = CodeChunk(
        index_version_id=index_version.id,
        file_id=file_obj.id,
        repository_id=repo.id,
        chunk_index=0,
        chunk_type=ChunkType.CLASS,
        symbol_name="AESCipher",
        start_line=1,
        end_line=15,
        content="class AESCipher:\n    def encrypt(self, data: str) -> str:\n        return 'encrypted'",
        context_header="# File: src/security/encryption.py | Class: AESCipher",
        token_count=35,
    )
    db_session.add(chunk1)
    await db_session.flush()

    emb1 = ChunkEmbedding(
        chunk_id=chunk1.id,
        index_version_id=index_version.id,
        repository_id=repo.id,
        provider="google",
        model="gemini-embedding-2",
        dimension=768,
        embedding_version=1,
        embedding=[0.1] * 768,
    )
    db_session.add(emb1)

    await db_session.commit()

    return {
        "org": org,
        "project": project,
        "repo": repo,
        "branch": branch,
        "index_version": index_version,
        "file": file_obj,
        "chunk": chunk1,
    }


@pytest.mark.asyncio
async def test_trigger_repository_indexing(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
):
    project = seeded_project_and_index["project"]
    repo = seeded_project_and_index["repo"]

    with patch(
        "app.services.ingestion.engine.IngestionEngine.run_indexing", new_callable=AsyncMock
    ) as mock_run:
        mock_run.return_value = uuid.uuid4()

        response = await client.post(
            f"/api/v1/projects/{project.id}/repositories/{repo.id}/index",
            json={"is_full_reindex": False},
            headers=auth_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["repository_id"] == str(repo.id)
        assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_indexing_status(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
):
    project = seeded_project_and_index["project"]
    repo = seeded_project_and_index["repo"]

    # First trigger index to create job
    with patch(
        "app.services.ingestion.engine.IngestionEngine.run_indexing", new_callable=AsyncMock
    ):
        await client.post(
            f"/api/v1/projects/{project.id}/repositories/{repo.id}/index",
            json={"is_full_reindex": False},
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/v1/projects/{project.id}/repositories/{repo.id}/index/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == str(repo.id)
        assert "status" in data


@pytest.mark.asyncio
async def test_trigger_repository_indexing_enqueues_arq_job(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
):
    """Verifies that trigger_repository_indexing enqueues the job to ARQ queue with correct parameters."""
    project = seeded_project_and_index["project"]
    repo = seeded_project_and_index["repo"]
    branch = seeded_project_and_index["branch"]

    mock_arq_pool = AsyncMock()
    mock_arq_pool.enqueue_job = AsyncMock()

    with patch("app.api.v1.ingestion.get_arq_pool", return_value=mock_arq_pool):
        response = await client.post(
            f"/api/v1/projects/{project.id}/repositories/{repo.id}/index",
            json={"is_full_reindex": True, "branch_id": str(branch.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        job_id = data["job_id"]

        # Assert ARQ enqueue was invoked with correct arguments
        mock_arq_pool.enqueue_job.assert_called_once_with(
            "index_repository_task",
            str(repo.id),
            str(branch.id),
            is_full_reindex=True,
            job_id=job_id,
        )


@pytest.mark.asyncio
async def test_trigger_indexing_concurrency_returns_active_job(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
    db_session,
):
    """Verifies that triggering indexing while a job is in progress returns the existing active job instead of spawning a new one."""
    project = seeded_project_and_index["project"]
    repo = seeded_project_and_index["repo"]
    branch = seeded_project_and_index["branch"]

    from app.models.codebase import IndexingJob, IndexingJobStatus

    # Create an active job
    active_job = IndexingJob(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha=repo.default_branch,
        status=IndexingJobStatus.PARSING,
        total_files=50,
        processed_files=20,
    )
    db_session.add(active_job)
    await db_session.commit()

    mock_arq_pool = AsyncMock()
    mock_arq_pool.enqueue_job = AsyncMock()

    with patch("app.api.v1.ingestion.get_arq_pool", return_value=mock_arq_pool):
        response = await client.post(
            f"/api/v1/projects/{project.id}/repositories/{repo.id}/index",
            json={"is_full_reindex": False, "branch_id": str(branch.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == str(active_job.id)
        assert data["status"] == "parsing"
        assert data["total_files"] == 50
        assert data["processed_files"] == 20

        # Verify that NO new job was enqueued
        mock_arq_pool.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_hybrid_search_evidence_retrieval(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
):
    project = seeded_project_and_index["project"]

    # Mock embed_query for Gemini
    with patch(
        "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = [0.1] * 768

        response = await client.post(
            f"/api/v1/projects/{project.id}/search/hybrid",
            json={"query": "AESCipher encrypt data", "top_k": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "AESCipher encrypt data"
        assert data["total_results"] >= 1

        top_chunk = data["results"][0]
        assert top_chunk["file_path"] == "src/security/encryption.py"
        assert top_chunk["symbol_name"] == "AESCipher"
        assert top_chunk["start_line"] == 1
        assert top_chunk["end_line"] == 15
        assert top_chunk["rrf_score"] > 0
        assert top_chunk["commit_sha"] == "c0ffee1234567890abcdef1234567890abcdef12"


@pytest.mark.asyncio
async def test_list_indexed_files_and_details(
    client: AsyncClient,
    seeded_project_and_index: dict,
    auth_headers: dict[str, str],
):
    project = seeded_project_and_index["project"]
    file_obj = seeded_project_and_index["file"]

    # 1. List files
    files_resp = await client.get(
        f"/api/v1/projects/{project.id}/files",
        headers=auth_headers,
    )
    assert files_resp.status_code == 200
    files_data = files_resp.json()
    assert len(files_data) == 1
    assert files_data[0]["file_path"] == "src/security/encryption.py"
    assert files_data[0]["chunks_count"] == 1

    # 2. Get file detail
    detail_resp = await client.get(
        f"/api/v1/projects/{project.id}/files/{file_obj.id}",
        headers=auth_headers,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["file_path"] == "src/security/encryption.py"
    assert len(detail_data["chunks"]) == 1
    assert detail_data["chunks"][0]["symbol_name"] == "AESCipher"


@pytest.mark.asyncio
async def test_tenant_isolation_rejects_unauthorized_user(
    client: AsyncClient,
    seeded_project_and_index: dict,
    db_session,
):
    project = seeded_project_and_index["project"]

    # Create another user in a separate organization
    other_user = User(
        email="outsider@acme.com",
        hashed_password="hashed_password",
        full_name="Outsider User",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()

    from app.core.security import create_access_token

    outsider_token = create_access_token(other_user.id)
    outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

    # Should be rejected with 403 Forbidden
    response = await client.get(
        f"/api/v1/projects/{project.id}/files",
        headers=outsider_headers,
    )
    assert response.status_code == 403
