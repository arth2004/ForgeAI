import os
from typing import ClassVar

from app.core.config import settings


class IngestionFilter:
    """Filters ignored directories, vendor bundles, lockfiles, generated assets, and binary files."""

    IGNORED_DIRS: ClassVar[set[str]] = {
        ".git",
        ".github",
        "node_modules",
        "dist",
        "build",
        "out",
        ".next",
        "target",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".cache",
        ".idea",
        ".vscode",
        "vendor",
        "coverage",
        ".turbo",
    }

    IGNORED_FILES: ClassVar[set[str]] = {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pipfile.lock",
        "cargo.lock",
        "go.sum",
        "composer.lock",
        ".ds_store",
        "thumbs.db",
    }

    BINARY_EXTENSIONS: ClassVar[set[str]] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".webp",
        ".mp4",
        ".webm",
        ".mov",
        ".mp3",
        ".wav",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".7z",
        ".rar",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".pyc",
        ".pyo",
        ".pyd",
        ".class",
        ".jar",
        ".wasm",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".parquet",
        ".arrow",
    }

    MINIFIED_EXTENSIONS: ClassVar[set[str]] = {
        ".min.js",
        ".min.css",
        ".bundle.js",
        ".bundle.css",
        ".map",
    }

    @classmethod
    def should_ignore_path(cls, file_path: str) -> bool:
        """Determines if a relative file path should be ignored before reading contents."""
        normalized = file_path.replace("\\", "/").strip("/")
        parts = normalized.split("/")

        # Check directory names
        for part in parts[:-1]:
            if part.lower() in cls.IGNORED_DIRS or part.startswith("."):
                return True

        filename = parts[-1].lower() if parts else ""

        # Check exact ignored file names
        if filename in cls.IGNORED_FILES:
            return True

        # Check minified/bundle suffixes
        for min_ext in cls.MINIFIED_EXTENSIONS:
            if filename.endswith(min_ext):
                return True

        # Check binary extensions
        _, ext = os.path.splitext(filename)
        if ext in cls.BINARY_EXTENSIONS:
            return True

        return False

    @classmethod
    def is_binary_content(cls, data: bytes) -> bool:
        """Checks if byte content contains null bytes or cannot decode as UTF-8."""
        if b"\x00" in data[:1024]:
            return True
        try:
            data.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True

    @classmethod
    def is_within_size_limit(cls, size_bytes: int) -> bool:
        """Validates that file size does not exceed the configurable limit."""
        return size_bytes <= settings.MAX_FILE_SIZE_BYTES
