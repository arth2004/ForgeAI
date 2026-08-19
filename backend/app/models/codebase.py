import datetime
import enum
import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.project import Repository, RepositoryBranch


class TsVector(TypeDecorator):
    """PostgreSQL TSVECTOR with SQLite fallback for unit tests."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class IndexVersionStatus(enum.StrEnum):
    BUILDING = "building"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class ChunkType(enum.StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    MODULE = "module"
    BLOCK = "block"
    MARKDOWN_SECTION = "markdown_section"
    DATA_BLOCK = "data_block"


class DependencyType(enum.StrEnum):
    IMPORT = "import"
    CALL = "call"
    INHERITANCE = "inheritance"
    IMPLEMENTATION = "implementation"


class IndexingJobStatus(enum.StrEnum):
    PENDING = "pending"
    ACQUIRING = "acquiring"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class RepositoryIndexVersion(Base):
    """Tracks atomic index versions for a repository branch."""

    __tablename__ = "repository_index_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repository_branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[IndexVersionStatus] = mapped_column(
        Enum(IndexVersionStatus, native_enum=False, length=32),
        default=IndexVersionStatus.BUILDING,
        nullable=False,
        index=True,
    )
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", foreign_keys=[repository_id])
    branch: Mapped["RepositoryBranch"] = relationship("RepositoryBranch", foreign_keys=[branch_id])
    files: Mapped[list["RepositoryFile"]] = relationship(
        "RepositoryFile", back_populates="index_version", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk", back_populates="index_version", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding", back_populates="index_version", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["CodeDependency"]] = relationship(
        "CodeDependency", back_populates="index_version", cascade="all, delete-orphan"
    )


class RepositoryFile(Base):
    """Inventory of indexed files for a repository index version with content hashes."""

    __tablename__ = "repository_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    index_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("repository_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("index_version_id", "file_path", name="uq_repo_file_version_path"),
    )

    index_version: Mapped["RepositoryIndexVersion"] = relationship(
        "RepositoryIndexVersion", back_populates="files"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk", back_populates="file", cascade="all, delete-orphan"
    )


class CodeChunk(Base):
    """Semantic code chunk bounded by AST syntax grammar."""

    __tablename__ = "code_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    index_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("repository_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[ChunkType] = mapped_column(
        Enum(ChunkType, native_enum=False, length=32), nullable=False
    )
    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_header: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(
        TsVector,
        server_default=FetchedValue(),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    index_version: Mapped["RepositoryIndexVersion"] = relationship(
        "RepositoryIndexVersion", back_populates="chunks"
    )
    file: Mapped["RepositoryFile"] = relationship("RepositoryFile", back_populates="chunks")
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding", back_populates="chunk", cascade="all, delete-orphan"
    )


class ChunkEmbedding(Base):
    """Vector representation of code chunk in 768d space (gemini-embedding-2)."""

    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("code_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("repository_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="google", nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="gemini-embedding-2", nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, default=768, nullable=False)
    embedding_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "chunk_id", "provider", "model", "embedding_version", name="uq_chunk_embed_version"
        ),
    )

    chunk: Mapped["CodeChunk"] = relationship("CodeChunk", back_populates="embeddings")
    index_version: Mapped["RepositoryIndexVersion"] = relationship(
        "RepositoryIndexVersion", back_populates="embeddings"
    )


class CodeDependency(Base):
    """Import and dependency relationship model."""

    __tablename__ = "code_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    index_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("repository_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_symbol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_symbol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, native_enum=False, length=32),
        default=DependencyType.IMPORT,
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    index_version: Mapped["RepositoryIndexVersion"] = relationship(
        "RepositoryIndexVersion", back_populates="dependencies"
    )


class IndexingJob(Base):
    """Background ARQ indexing job execution and telemetry record."""

    __tablename__ = "indexing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repository_branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("repository_index_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[IndexingJobStatus] = mapped_column(
        Enum(IndexingJobStatus, native_enum=False, length=32),
        default=IndexingJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedded_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
