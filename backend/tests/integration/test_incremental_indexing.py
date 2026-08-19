import io
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.auth import Membership, Organization, Role, User
from app.models.codebase import IndexVersionStatus, RepositoryIndexVersion
from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch
from app.services.ingestion.engine import IngestionEngine
from tests.conftest import TestingSessionLocal


def create_mock_tarball(files: dict[str, str]) -> bytes:
    """Helper to create in-memory .tar.gz byte payload for tests."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in files.items():
            data = content.encode("utf-8")
            ti = tarfile.TarInfo(name=f"owner-repo-sha/{path}")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


@pytest_asyncio.fixture(scope="function")
async def setup_repo_for_ingestion(db_session, test_user: User):
    org = Organization(name="Core Org", slug="core-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    test_user.github_installation_id = 999111
    db_session.add(test_user)

    project = Project(organization_id=org.id, name="Core Engine", description="Core")
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        github_repo_id=123987,
        owner="core-org",
        full_name="core-org/core-engine",
        default_branch="main",
        indexing_status=IndexingStatus.pending,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="sha_initial_1111",
        is_protected=False,
    )
    db_session.add(branch)
    await db_session.commit()

    return {
        "org": org,
        "project": project,
        "repo": repo,
        "branch": branch,
    }


@pytest.mark.asyncio
async def test_full_and_incremental_indexing_workflow(
    setup_repo_for_ingestion: dict,
    db_session,
):
    repo = setup_repo_for_ingestion["repo"]
    branch = setup_repo_for_ingestion["branch"]

    initial_files = {
        "src/auth.py": "def login():\n    return True\n",
        "src/utils.py": "def helper():\n    return 42\n",
        "src/deleted.py": "def old_fn():\n    pass\n",
    }
    initial_tarball_bytes = create_mock_tarball(initial_files)

    mock_branch_resp = AsyncMock()
    mock_branch_resp.json.return_value = {"commit": {"sha": "sha_v1_commit"}}

    async def mock_aiter_v1(*args, **kwargs):
        yield initial_tarball_bytes

    mock_stream_resp = AsyncMock()
    mock_stream_resp.status_code = 200
    mock_stream_resp.aiter_bytes = mock_aiter_v1

    # 1. Full Initial Indexing
    with (
        patch(
            "app.services.github.client.github_client.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_token,
        patch(
            "app.services.github.client.github_client._request", new_callable=AsyncMock
        ) as mock_req,
        patch("httpx.AsyncClient.stream") as mock_stream,
        patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_documents",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_token.return_value = "ghs_mock_token"
        mock_req.return_value = mock_branch_resp

        # Mock stream context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_stream_resp
        mock_stream.return_value = mock_ctx

        # Mock embeddings
        mock_embed.side_effect = lambda texts: [[0.1] * 768 for _ in texts]

        v1_id = await IngestionEngine.run_indexing(
            repository_id=repo.id,
            branch_id=branch.id,
            is_full_reindex=True,
            session_factory=TestingSessionLocal,
        )

        assert v1_id is not None

        # Verify Index Version 1 is ACTIVE
        v1_ver = await db_session.get(RepositoryIndexVersion, v1_id)
        assert v1_ver.status == IndexVersionStatus.ACTIVE
        assert v1_ver.commit_sha == "sha_v1_commit"
        assert v1_ver.total_files == 3

    # 2. Incremental Indexing (Modify auth.py, Keep utils.py, Add config.py, Delete deleted.py)
    updated_files = {
        "src/auth.py": "def login():\n    # updated\n    return False\n",
        "src/utils.py": "def helper():\n    return 42\n",  # Unchanged
        "src/config.py": "API_KEY = 'secret'\n",  # Added
    }
    updated_tarball_bytes = create_mock_tarball(updated_files)

    mock_branch_v2_resp = AsyncMock()
    mock_branch_v2_resp.json.return_value = {"commit": {"sha": "sha_v2_commit"}}

    async def mock_aiter_v2(*args, **kwargs):
        yield updated_tarball_bytes

    mock_stream_v2_resp = AsyncMock()
    mock_stream_v2_resp.status_code = 200
    mock_stream_v2_resp.aiter_bytes = mock_aiter_v2

    with (
        patch(
            "app.services.github.client.github_client.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_token,
        patch(
            "app.services.github.client.github_client._request", new_callable=AsyncMock
        ) as mock_req,
        patch("httpx.AsyncClient.stream") as mock_stream,
        patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_documents",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_token.return_value = "ghs_mock_token"
        mock_req.return_value = mock_branch_v2_resp

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_stream_v2_resp
        mock_stream.return_value = mock_ctx

        mock_embed.side_effect = lambda texts: [[0.2] * 768 for _ in texts]

        v2_id = await IngestionEngine.run_indexing(
            repository_id=repo.id,
            branch_id=branch.id,
            is_full_reindex=False,
            session_factory=TestingSessionLocal,
        )

        assert v2_id != v1_id

        # Verify Index Version 2 is ACTIVE and Version 1 is SUPERSEDED
        await db_session.refresh(v1_ver)
        assert v1_ver.status == IndexVersionStatus.SUPERSEDED

        v2_ver = await db_session.get(RepositoryIndexVersion, v2_id)
        assert v2_ver.status == IndexVersionStatus.ACTIVE
        assert v2_ver.commit_sha == "sha_v2_commit"
        assert v2_ver.total_files == 3  # auth.py, utils.py, config.py


@pytest.mark.asyncio
async def test_failed_indexing_retains_previous_active_index(
    setup_repo_for_ingestion: dict,
    db_session,
):
    repo = setup_repo_for_ingestion["repo"]
    branch = setup_repo_for_ingestion["branch"]

    # 1. Establish an initial ACTIVE index version
    active_ver = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="stable_sha_1234",
        status=IndexVersionStatus.ACTIVE,
        total_files=2,
        total_chunks=4,
    )
    db_session.add(active_ver)
    await db_session.commit()

    # 2. Trigger an indexing attempt that raises an exception (e.g. tarball corruption)
    with (
        patch(
            "app.services.github.client.github_client.get_installation_access_token",
            new_callable=AsyncMock,
        ) as mock_token,
        patch(
            "app.services.github.client.github_client._request", new_callable=AsyncMock
        ) as mock_req,
        patch("httpx.AsyncClient.stream", side_effect=Exception("Fatal tarball download failure")),
    ):
        mock_token.return_value = "ghs_mock_token"
        mock_branch_resp = AsyncMock()
        mock_branch_resp.json.return_value = {"commit": {"sha": "new_broken_sha"}}
        mock_req.return_value = mock_branch_resp

        with pytest.raises(Exception, match="Fatal tarball download failure"):
            await IngestionEngine.run_indexing(
                repository_id=repo.id,
                branch_id=branch.id,
                is_full_reindex=False,
                session_factory=TestingSessionLocal,
            )

        # 3. Verify that the previous ACTIVE version is STILL ACTIVE
        await db_session.refresh(active_ver)
        assert active_ver.status == IndexVersionStatus.ACTIVE

        # Verify repository is back to ready
        await db_session.refresh(repo)
        assert repo.indexing_status == IndexingStatus.ready


@pytest.mark.asyncio
async def test_quota_exhausted_indexing_failure_preserves_active_and_sets_user_friendly_error(
    setup_repo_for_ingestion: dict,
    db_session,
):
    """Verifies that EmbeddingQuotaExhaustedException during indexing updates job error_message with safe user text and preserves active index."""
    repo = setup_repo_for_ingestion["repo"]
    branch = setup_repo_for_ingestion["branch"]

    # 1. Establish an initial ACTIVE index version
    active_ver = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="stable_sha_prior",
        status=IndexVersionStatus.ACTIVE,
        total_files=1,
        total_chunks=2,
    )
    db_session.add(active_ver)
    await db_session.commit()

    from app.core.exceptions import EmbeddingQuotaExhaustedException
    from app.models.codebase import IndexingJob, IndexingJobStatus

    # Create job record
    job = IndexingJob(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="new_sha_quota",
        status=IndexingJobStatus.PENDING,
    )
    db_session.add(job)
    await db_session.commit()

    mock_tarball_bytes = create_mock_tarball({"main.py": "print('hello world')\n"})

    async def mock_aiter(*args, **kwargs):
        yield mock_tarball_bytes

    mock_stream = AsyncMock()
    mock_stream.status_code = 200
    mock_stream.aiter_bytes = mock_aiter

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.github.client.github_client.get_installation_access_token",
            new_callable=AsyncMock,
            return_value="ghs_mock",
        ),
        patch(
            "app.services.github.client.github_client._request",
            new_callable=AsyncMock,
            return_value=AsyncMock(json=lambda: {"commit": {"sha": "new_sha_quota"}}),
        ),
        patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx),
        patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_documents",
            side_effect=EmbeddingQuotaExhaustedException(
                "Gemini embedding quota exhausted. Indexing can resume when the provider quota resets or billing/quota is increased."
            ),
        ),
    ):
        with pytest.raises(EmbeddingQuotaExhaustedException):
            await IngestionEngine.run_indexing(
                repository_id=repo.id,
                branch_id=branch.id,
                is_full_reindex=False,
                job_id=job.id,
                session_factory=TestingSessionLocal,
            )

        # 2. Check that previous ACTIVE index is still ACTIVE
        await db_session.refresh(active_ver)
        assert active_ver.status == IndexVersionStatus.ACTIVE

        # 3. Check that the job status is FAILED with the exact safe user-facing message
        await db_session.refresh(job)
        assert job.status == IndexingJobStatus.FAILED
        assert job.error_message == "Gemini embedding quota exhausted. Indexing can resume when the provider quota resets or billing/quota is increased."

        # Verify no secret leakage in error message
        assert "AIza" not in job.error_message
        assert "key=" not in job.error_message


@pytest.mark.asyncio
async def test_superseded_version_cleanup_retention(
    setup_repo_for_ingestion: dict,
    db_session,
):
    """Verifies that cleanup_superseded_versions purges versions exceeding retention limit and cascades to files/chunks/embeddings."""
    repo = setup_repo_for_ingestion["repo"]
    branch = setup_repo_for_ingestion["branch"]

    from app.models.codebase import (
        ChunkEmbedding,
        CodeChunk,
        RepositoryFile,
    )

    # 1. Create 1 ACTIVE version and 5 SUPERSEDED versions
    active_ver = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="sha_active",
        status=IndexVersionStatus.ACTIVE,
        total_files=1,
        total_chunks=1,
    )
    db_session.add(active_ver)
    await db_session.flush()

    superseded_versions = []
    for i in range(5):
        ver = RepositoryIndexVersion(
            repository_id=repo.id,
            branch_id=branch.id,
            commit_sha=f"sha_superseded_{i}",
            status=IndexVersionStatus.SUPERSEDED,
            total_files=1,
            total_chunks=1,
        )
        db_session.add(ver)
        await db_session.flush()
        superseded_versions.append(ver)

        # Add a file, chunk, and embedding to verify cascade deletion
        f = RepositoryFile(
            index_version_id=ver.id,
            repository_id=repo.id,
            file_path=f"src/file_{i}.py",
            file_name=f"file_{i}.py",
            extension=".py",
            language="python",
            size_bytes=100,
            content_hash=f"hash_{i}",
            is_binary=False,
        )
        db_session.add(f)
        await db_session.flush()

        c = CodeChunk(
            index_version_id=ver.id,
            file_id=f.id,
            repository_id=repo.id,
            chunk_index=0,
            chunk_type="function",
            symbol_name=f"fn_{i}",
            start_line=1,
            end_line=5,
            content=f"def fn_{i}(): pass",
            context_header=f"# file: file_{i}.py",
            token_count=10,
        )
        db_session.add(c)
        await db_session.flush()

        emb = ChunkEmbedding(
            chunk_id=c.id,
            index_version_id=ver.id,
            repository_id=repo.id,
            provider="google",
            model="gemini-embedding-2",
            dimension=768,
            embedding_version=1,
            embedding=[0.1] * 768,
        )
        db_session.add(emb)

    await db_session.commit()

    # Retention limit = 2 (should delete 3 oldest superseded versions, keep 2 most recent)
    deleted_count = await IngestionEngine.cleanup_superseded_versions(
        db_session, branch_id=branch.id, retention_count=2
    )
    assert deleted_count == 3
    await db_session.commit()

    # Active version must remain intact
    await db_session.refresh(active_ver)
    assert active_ver.status == IndexVersionStatus.ACTIVE

    # Check remaining versions
    from sqlalchemy import select

    remaining_res = await db_session.execute(
        select(RepositoryIndexVersion).where(RepositoryIndexVersion.branch_id == branch.id)
    )
    remaining = remaining_res.scalars().all()
    # 1 ACTIVE + 2 retained SUPERSEDED = 3 total
    assert len(remaining) == 3

    # Check that deleted version's chunks and embeddings were deleted via cascade
    oldest_deleted_id = superseded_versions[0].id
    old_chunks = (
        await db_session.execute(
            select(CodeChunk).where(CodeChunk.index_version_id == oldest_deleted_id)
        )
    ).scalars().all()
    assert len(old_chunks) == 0

    # Idempotency check: running cleanup again deletes 0
    deleted_again = await IngestionEngine.cleanup_superseded_versions(
        db_session, branch_id=branch.id, retention_count=2
    )
    assert deleted_again == 0


@pytest.mark.asyncio
async def test_concurrency_guard_rejects_duplicate_active_indexing(
    setup_repo_for_ingestion: dict,
    db_session,
):
    """Verifies that run_indexing raises ForgeAIException (409) when an active indexing job is already in progress."""
    repo = setup_repo_for_ingestion["repo"]
    branch = setup_repo_for_ingestion["branch"]

    from app.core.exceptions import ForgeAIException
    from app.models.codebase import IndexingJob, IndexingJobStatus

    # Create an in-flight job on this branch
    active_job = IndexingJob(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="sha_in_flight",
        status=IndexingJobStatus.EMBEDDING,
    )
    db_session.add(active_job)
    await db_session.commit()

    # Attempt to run a second indexing operation on the same branch
    with pytest.raises(ForgeAIException) as exc_info:
        await IngestionEngine.run_indexing(
            repository_id=repo.id,
            branch_id=branch.id,
            session_factory=TestingSessionLocal,
        )

    assert exc_info.value.status_code == 409
    assert "already in progress" in str(exc_info.value)

