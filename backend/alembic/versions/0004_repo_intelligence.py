"""Create repository intelligence tables and pgvector HNSW index

Revision ID: 0004_repo_intelligence
Revises: 0003_drop_github_token
Create Date: 2026-08-16 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_repo_intelligence"
down_revision: str | None = "0003_drop_github_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension if not present
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create repository_index_versions table
    op.create_table(
        "repository_index_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["repository_branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repository_index_versions_repository_id",
        "repository_index_versions",
        ["repository_id"],
    )
    op.create_index(
        "ix_repository_index_versions_branch_id",
        "repository_index_versions",
        ["branch_id"],
    )
    op.create_index(
        "ix_repository_index_versions_status",
        "repository_index_versions",
        ["status"],
    )

    # 3. Create repository_files table
    op.create_table(
        "repository_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_binary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["repository_index_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_version_id", "file_path", name="uq_repo_file_version_path"),
    )
    op.create_index(
        "ix_repository_files_index_version_id",
        "repository_files",
        ["index_version_id"],
    )
    op.create_index(
        "ix_repository_files_repository_id",
        "repository_files",
        ["repository_id"],
    )
    op.create_index(
        "ix_repository_files_content_hash",
        "repository_files",
        ["content_hash"],
    )

    # 4. Create code_chunks table
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=32), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_header", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["repository_index_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["file_id"], ["repository_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_chunks_index_version_id", "code_chunks", ["index_version_id"])
    op.create_index("ix_code_chunks_file_id", "code_chunks", ["file_id"])
    op.create_index("ix_code_chunks_repository_id", "code_chunks", ["repository_id"])
    op.create_index("ix_code_chunks_symbol_name", "code_chunks", ["symbol_name"])

    # Add tsvector generated column and GIN index on code_chunks
    op.execute(
        """
        ALTER TABLE code_chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(symbol_name, '')), 'A') ||
            setweight(to_tsvector('english', context_header), 'B') ||
            setweight(to_tsvector('english', content), 'C')
        ) STORED;
        """
    )
    op.create_index(
        "ix_code_chunks_search_vector",
        "code_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 5. Create chunk_embeddings table with Vector(768) and HNSW index
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="google", nullable=False),
        sa.Column(
            "model", sa.String(length=64), server_default="gemini-embedding-2", nullable=False
        ),
        sa.Column("dimension", sa.Integer(), server_default="768", nullable=False),
        sa.Column("embedding_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["repository_index_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id", "provider", "model", "embedding_version", name="uq_chunk_embed_version"
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_index_version_id", "chunk_embeddings", ["index_version_id"]
    )
    op.create_index("ix_chunk_embeddings_repository_id", "chunk_embeddings", ["repository_id"])

    # Create HNSW index for cosine distance
    op.execute(
        """
        CREATE INDEX ix_chunk_embeddings_hnsw ON chunk_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # 6. Create code_dependencies table
    op.create_table(
        "code_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("source_symbol", sa.String(length=255), nullable=True),
        sa.Column("target_symbol", sa.String(length=255), nullable=True),
        sa.Column("imported_path", sa.String(length=1024), nullable=False),
        sa.Column("dependency_type", sa.String(length=32), server_default="import", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["repository_index_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["file_id"], ["repository_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_code_dependencies_index_version_id",
        "code_dependencies",
        ["index_version_id"],
    )
    op.create_index(
        "ix_code_dependencies_imported_path",
        "code_dependencies",
        ["imported_path"],
    )

    # 7. Create indexing_jobs table
    op.create_table(
        "indexing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("index_version_id", sa.Uuid(), nullable=True),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("total_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedded_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["repository_branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["repository_index_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_indexing_jobs_repository_id",
        "indexing_jobs",
        ["repository_id"],
    )
    op.create_index(
        "ix_indexing_jobs_status",
        "indexing_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("indexing_jobs")
    op.drop_table("code_dependencies")
    op.drop_table("chunk_embeddings")
    op.drop_table("code_chunks")
    op.drop_table("repository_files")
    op.drop_table("repository_index_versions")
