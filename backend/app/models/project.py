import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class IndexingStatus(enum.StrEnum):
    pending = "pending"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository", back_populates="project", cascade="all, delete-orphan"
    )


class Repository(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "repositories"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_repo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    html_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    indexing_status: Mapped[IndexingStatus] = mapped_column(
        Enum(IndexingStatus, name="indexing_status_enum", native_enum=False), default=IndexingStatus.pending, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="repositories")
    branches: Mapped[list["RepositoryBranch"]] = relationship(
        "RepositoryBranch", back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryBranch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "repository_branches"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_repo_branch_name"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="branches")


from app.models.auth import Organization  # noqa: E402
