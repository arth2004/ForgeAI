import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment before imports
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_SECRET"] = "test-secret-key-that-is-at-least-32-chars-long-forgeai"
os.environ["ENCRYPTION_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

import app.core.database
import app.models  # noqa: F401
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models.auth import User
from app.models.base import Base

# Shared in-memory SQLite async engine with StaticPool so all connections and threads share the same database
test_engine = create_async_engine(
    "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true",
    connect_args={"check_same_thread": False, "uri": True},
    poolclass=StaticPool,
    echo=False,
    future=True,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Patch global AsyncSessionLocal in app.core.database to use the shared test engine
app.core.database.AsyncSessionLocal = TestingSessionLocal


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database schema for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client overriding get_db dependency."""

    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Creates a standard test user in the database."""
    user = User(
        email="developer@forgeai.dev",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Forge Developer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(test_user: User) -> dict[str, str]:
    """Generates valid Bearer authentication headers for test_user."""
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def indexed_tool_repo(db_session: AsyncSession, test_user: User):
    """Creates an indexed repository fixture with source code and documentation files for agent tool tests."""
    from app.models.auth import Membership, Organization, Role
    from app.models.codebase import (
        ChunkEmbedding,
        ChunkType,
        CodeChunk,
        IndexVersionStatus,
        RepositoryFile,
        RepositoryIndexVersion,
    )
    from app.models.project import IndexingStatus, Project, Repository, RepositoryBranch

    org = Organization(name="Tool Testing Org", slug="tool-testing-org")
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=test_user.id, organization_id=org.id, role=Role.owner)
    db_session.add(membership)

    project = Project(organization_id=org.id, name="Tool Test Project", description="Agent tool tests")
    db_session.add(project)
    await db_session.flush()

    repo = Repository(
        project_id=project.id,
        github_repo_id=123456,
        owner="forgeai-tools",
        full_name="forgeai-tools/repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(repo)
    await db_session.flush()

    branch = RepositoryBranch(
        repository_id=repo.id,
        name="main",
        latest_commit_sha="commit_sha_123",
        is_protected=False,
    )
    db_session.add(branch)
    await db_session.flush()

    index_ver = RepositoryIndexVersion(
        repository_id=repo.id,
        branch_id=branch.id,
        commit_sha="commit_sha_123",
        status=IndexVersionStatus.ACTIVE,
        total_files=3,
        total_chunks=6,
    )
    db_session.add(index_ver)
    await db_session.flush()

    # 1. Code file: backend/app/services/embedding/gemini.py
    file_code = RepositoryFile(
        index_version_id=index_ver.id,
        repository_id=repo.id,
        file_path="backend/app/services/embedding/gemini.py",
        file_name="gemini.py",
        extension=".py",
        language="python",
        size_bytes=1024,
        content_hash="hash_gemini_py",
    )
    db_session.add(file_code)
    await db_session.flush()

    chunk_gemini_class = CodeChunk(
        index_version_id=index_ver.id,
        file_id=file_code.id,
        repository_id=repo.id,
        chunk_index=0,
        chunk_type=ChunkType.CLASS,
        symbol_name="GeminiEmbeddingProvider",
        start_line=10,
        end_line=45,
        context_header="class GeminiEmbeddingProvider(BaseEmbeddingProvider):",
        content="class GeminiEmbeddingProvider(BaseEmbeddingProvider):\n    async def embed_documents(self, texts):\n        return [[0.1]*768]",
        token_count=50,
    )
    chunk_gemini_method = CodeChunk(
        index_version_id=index_ver.id,
        file_id=file_code.id,
        repository_id=repo.id,
        chunk_index=1,
        chunk_type=ChunkType.METHOD,
        symbol_name="embed_documents",
        start_line=20,
        end_line=35,
        context_header="GeminiEmbeddingProvider.embed_documents",
        content="async def embed_documents(self, texts):\n    return [[0.1]*768]",
        token_count=30,
    )
    db_session.add_all([chunk_gemini_class, chunk_gemini_method])
    await db_session.flush()

    vec_gemini = [0.0] * 768
    vec_gemini[0] = 1.0
    db_session.add(ChunkEmbedding(chunk_id=chunk_gemini_class.id, index_version_id=index_ver.id, repository_id=repo.id, embedding=vec_gemini, dimension=768, provider="google", model="gemini-embedding-2"))
    db_session.add(ChunkEmbedding(chunk_id=chunk_gemini_method.id, index_version_id=index_ver.id, repository_id=repo.id, embedding=vec_gemini, dimension=768, provider="google", model="gemini-embedding-2"))

    # 2. Code file: backend/app/services/retrieval/hybrid.py
    file_hybrid = RepositoryFile(
        index_version_id=index_ver.id,
        repository_id=repo.id,
        file_path="backend/app/services/retrieval/hybrid.py",
        file_name="hybrid.py",
        extension=".py",
        language="python",
        size_bytes=2048,
        content_hash="hash_hybrid_py",
    )
    db_session.add(file_hybrid)
    await db_session.flush()

    chunk_hybrid = CodeChunk(
        index_version_id=index_ver.id,
        file_id=file_hybrid.id,
        repository_id=repo.id,
        chunk_index=0,
        chunk_type=ChunkType.CLASS,
        symbol_name="HybridSearchEngine",
        start_line=15,
        end_line=60,
        context_header="class HybridSearchEngine:",
        content="class HybridSearchEngine:\n    @classmethod\n    async def search(cls, project_id, query, top_k=5):\n        pass",
        token_count=60,
    )
    db_session.add(chunk_hybrid)
    await db_session.flush()

    vec_hybrid = [0.0] * 768
    vec_hybrid[3] = 1.0
    db_session.add(ChunkEmbedding(chunk_id=chunk_hybrid.id, index_version_id=index_ver.id, repository_id=repo.id, embedding=vec_hybrid, dimension=768, provider="google", model="gemini-embedding-2"))

    # 3. Documentation file: docs/architecture.md
    file_doc = RepositoryFile(
        index_version_id=index_ver.id,
        repository_id=repo.id,
        file_path="docs/architecture.md",
        file_name="architecture.md",
        extension=".md",
        language="markdown",
        size_bytes=4096,
        content_hash="hash_arch_md",
    )
    db_session.add(file_doc)
    await db_session.flush()

    chunk_doc = CodeChunk(
        index_version_id=index_ver.id,
        file_id=file_doc.id,
        repository_id=repo.id,
        chunk_index=0,
        chunk_type=ChunkType.MARKDOWN_SECTION,
        symbol_name="Embedding Architecture Overview",
        start_line=1,
        end_line=50,
        context_header="## Embedding Architecture Overview",
        content="# Architecture Overview\nThis document describes how embeddings and hybrid search work across Forge AI.",
        token_count=80,
    )
    db_session.add(chunk_doc)
    await db_session.flush()

    vec_doc = [0.0] * 768
    vec_doc[0] = 0.5
    db_session.add(ChunkEmbedding(chunk_id=chunk_doc.id, index_version_id=index_ver.id, repository_id=repo.id, embedding=vec_doc, dimension=768, provider="google", model="gemini-embedding-2"))
    await db_session.commit()

    return {
        "project": project,
        "repository": repo,
        "branch": branch,
        "index_version": index_ver,
        "files": [file_code, file_hybrid, file_doc],
    }

