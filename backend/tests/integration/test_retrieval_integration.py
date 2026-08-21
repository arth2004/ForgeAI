import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codebase import (
    ChunkEmbedding,
    ChunkType,
    CodeChunk,
    IndexVersionStatus,
    RepositoryFile,
    RepositoryIndexVersion,
)
from app.models.project import Project, Repository, RepositoryBranch
from app.services.retrieval.hybrid import HybridSearchEngine


@pytest.mark.asyncio
async def test_hybrid_search_end_to_end_ranking(db_session: AsyncSession):
    # 1. Setup Project, Repo, Branch, Active Index Version
    project_id = uuid.uuid4()
    org_id = uuid.uuid4()
    project = Project(id=project_id, organization_id=org_id, name="Test Retrieval Project")
    db_session.add(project)

    repo_id = uuid.uuid4()
    repo = Repository(
        id=repo_id, project_id=project_id, full_name="org/retrieval-test", default_branch="main"
    )
    db_session.add(repo)

    branch_id = uuid.uuid4()
    branch = RepositoryBranch(
        id=branch_id, repository_id=repo_id, name="main", latest_commit_sha="a" * 40
    )
    db_session.add(branch)

    version_id = uuid.uuid4()
    index_version = RepositoryIndexVersion(
        id=version_id,
        repository_id=repo_id,
        branch_id=branch_id,
        commit_sha="a" * 40,
        status=IndexVersionStatus.ACTIVE,
    )
    db_session.add(index_version)

    # 2. Add Code File (implementation) and Doc File (documentation)
    code_file = RepositoryFile(
        id=uuid.uuid4(),
        repository_id=repo_id,
        index_version_id=version_id,
        file_path="backend/app/services/parser/tree_sitter.py",
        file_name="tree_sitter.py",
        extension=".py",
        language="python",
        content_hash="hash1",
        size_bytes=1000,
    )
    doc_file = RepositoryFile(
        id=uuid.uuid4(),
        repository_id=repo_id,
        index_version_id=version_id,
        file_path="docs/decisions.md",
        file_name="decisions.md",
        extension=".md",
        language="markdown",
        content_hash="hash2",
        size_bytes=2000,
    )
    db_session.add_all([code_file, doc_file])

    # 3. Add Code Chunk (class TreeSitterParser) and Doc Chunk (ADR-004 markdown section)
    code_chunk_id = uuid.uuid4()
    code_chunk = CodeChunk(
        id=code_chunk_id,
        repository_id=repo_id,
        file_id=code_file.id,
        index_version_id=version_id,
        chunk_index=0,
        chunk_type=ChunkType.CLASS,
        start_line=10,
        end_line=50,
        token_count=50,
        content="class TreeSitterParser:\n    def parse_file(self, content: bytes):\n        pass",
        context_header="# File: backend/app/services/parser/tree_sitter.py | Class: TreeSitterParser",
        symbol_name="TreeSitterParser",
    )

    doc_chunk_id = uuid.uuid4()
    doc_chunk = CodeChunk(
        id=doc_chunk_id,
        repository_id=repo_id,
        file_id=doc_file.id,
        index_version_id=version_id,
        chunk_index=0,
        chunk_type=ChunkType.MARKDOWN_SECTION,
        start_line=1,
        end_line=20,
        token_count=30,
        content="# ADR-004: Tree-sitter AST Parsing\nContext: We use Tree-sitter for AST structural chunking.",
        context_header="# File: docs/decisions.md",
        symbol_name="ADR-004: Tree-sitter AST Parsing",
    )
    db_session.add_all([code_chunk, doc_chunk])

    # 4. Add Dummy Embeddings (768d)
    emb_vector = [0.1] * 768
    db_session.add(
        ChunkEmbedding(
            id=uuid.uuid4(),
            repository_id=repo_id,
            chunk_id=code_chunk.id,
            index_version_id=version_id,
            embedding=emb_vector,
        )
    )
    db_session.add(
        ChunkEmbedding(
            id=uuid.uuid4(),
            repository_id=repo_id,
            chunk_id=doc_chunk.id,
            index_version_id=version_id,
            embedding=emb_vector,
        )
    )

    await db_session.commit()

    # 5. Search for implementation: "Where is the Tree-sitter parser implemented?"
    results = await HybridSearchEngine.search(
        project_id=project_id,
        query="Where is the Tree-sitter parser implemented?",
        top_k=5,
        session_override=db_session,
    )

    assert len(results) >= 2
    # Verify code chunk is ranked #1 for implementation query
    assert results[0].file_path == "backend/app/services/parser/tree_sitter.py"
    assert results[0].symbol_name == "TreeSitterParser"
    assert results[0].chunk_type == "class"
