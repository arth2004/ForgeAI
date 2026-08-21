import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.file_viewer import FileViewerTool
from app.agent.tools.repository_search import RepositorySearchTool
from app.agent.tools.symbol_search import SymbolSearchTool
from app.agent.tools.validation import (
    RepositoryNotIndexedError,
    ToolAuthorizationError,
)
from app.models.auth import User
from app.models.codebase import IndexVersionStatus, RepositoryIndexVersion
from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch


@pytest.mark.asyncio
async def test_search_repository_tool_execution(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Verifies that search_repository tool retrieves ranked evidence chunks with metadata."""
    project = indexed_tool_repo["project"]
    search_tool = RepositorySearchTool()

    query_vec = [0.0] * 768
    query_vec[0] = 1.0

    with patch(
        "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
        new_callable=AsyncMock,
        return_value=query_vec,
    ):
        result = await search_tool.aexecute(
            db=db_session,
            user_id=test_user.id,
            query="Where are embeddings generated?",
            project_id=str(project.id),
            top_k=5,
        )

    assert result.success is True
    assert result.tool_name == "search_repository"
    data = result.data
    assert data["query"] == "Where are embeddings generated?"
    assert data["total_results"] > 0

    first_result = data["results"][0]
    assert "backend/app/services/embedding/gemini.py" in first_result["file_path"]
    assert first_result["symbol_name"] in {"GeminiEmbeddingProvider", "embed_documents"}
    assert first_result["commit_sha"] == "commit_sha_123"


@pytest.mark.asyncio
async def test_search_symbol_tool_execution(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Verifies that search_symbol tool locates indexed AST declarations."""
    project = indexed_tool_repo["project"]
    symbol_tool = SymbolSearchTool()

    result = await symbol_tool.aexecute(
        db=db_session,
        user_id=test_user.id,
        symbol_name="HybridSearchEngine",
        project_id=str(project.id),
        limit=5,
    )

    assert result.success is True
    assert result.tool_name == "search_symbol"
    data = result.data
    assert data["total_found"] >= 1

    sym = data["symbols"][0]
    assert sym["symbol_name"] == "HybridSearchEngine"
    assert sym["file_path"] == "backend/app/services/retrieval/hybrid.py"
    assert sym["start_line"] == 15
    assert "class HybridSearchEngine" in sym["content"]


@pytest.mark.asyncio
async def test_get_file_tool_execution_and_slicing(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Verifies that get_file tool retrieves indexed file contents and handles line window slicing."""
    project = indexed_tool_repo["project"]
    file_tool = FileViewerTool()

    # Full file retrieval
    res_full = await file_tool.aexecute(
        db=db_session,
        user_id=test_user.id,
        file_path="backend/app/services/embedding/gemini.py",
        project_id=str(project.id),
    )

    assert res_full.success is True
    assert res_full.data["file_path"] == "backend/app/services/embedding/gemini.py"
    assert "GeminiEmbeddingProvider" in res_full.data["content"]
    assert res_full.data["total_chunks"] == 2

    # Sliced line range retrieval
    res_sliced = await file_tool.aexecute(
        db=db_session,
        user_id=test_user.id,
        file_path="backend/app/services/embedding/gemini.py",
        project_id=str(project.id),
        start_line=1,
        end_line=2,
    )
    assert res_sliced.success is True
    assert res_sliced.data["line_range"] == "1-2"


@pytest.mark.asyncio
async def test_get_file_non_existent_file_handling(
    db_session: AsyncSession, test_user: User, indexed_tool_repo
):
    """Verifies graceful handling when a non-existent file path is requested."""
    project = indexed_tool_repo["project"]
    file_tool = FileViewerTool()

    res = await file_tool.aexecute(
        db=db_session,
        user_id=test_user.id,
        file_path="backend/app/non_existent.py",
        project_id=str(project.id),
    )

    assert res.success is False
    assert res.error is not None and "not found in active repository index" in res.error


@pytest.mark.asyncio
async def test_tool_authorization_tenant_isolation(db_session: AsyncSession, indexed_tool_repo):
    """Verifies that unauthorized users from other organizations cannot execute repository tools."""
    project = indexed_tool_repo["project"]
    unauthorized_user_id = uuid.uuid4()

    search_tool = RepositorySearchTool()
    with pytest.raises(ToolAuthorizationError):
        await search_tool.aexecute(
            db=db_session,
            user_id=unauthorized_user_id,
            query="test",
            project_id=str(project.id),
        )


@pytest.mark.asyncio
async def test_tool_index_status_guard_rejects_unindexed_repo(
    db_session: AsyncSession, test_user: User
):
    """Verifies that tools reject repository requests when index version is not ACTIVE."""
    from app.models.auth import Membership, Organization, Role

    org = Organization(name="Unindexed Org", slug="unindexed-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    project = Project(
        organization_id=org.id, name="Unindexed Project", description="Test unindexed"
    )
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        github_repo_id=999999,
        owner="forgeai",
        full_name="forgeai/building-repo",
        default_branch="main",
        indexing_status=IndexingStatus.indexing,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(repository_id=repo.id, name="main")
    db_session.add(branch)
    await db_session.flush()

    # Index version is BUILDING (not ACTIVE)
    building_ver = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="build_sha",
        status=IndexVersionStatus.BUILDING,
    )
    db_session.add(building_ver)
    await db_session.commit()

    search_tool = RepositorySearchTool()
    with pytest.raises(RepositoryNotIndexedError) as exc_info:
        await search_tool.aexecute(
            db=db_session,
            user_id=test_user.id,
            query="test query",
            project_id=str(project.id),
        )
    assert "No ACTIVE index version found" in exc_info.value.message
