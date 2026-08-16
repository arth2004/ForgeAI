import hashlib
import io
import logging
import tarfile
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import ForgeAIException
from app.services.ingestion.filters import IngestionFilter

logger = logging.getLogger(__name__)


@dataclass
class StreamedFileEntry:
    file_path: str
    content: str
    content_hash: str
    size_bytes: int


class StreamingTarballProcessor:
    """Streams and unpacks GitHub repository tarball archives without buffering the entire archive in RAM."""

    @classmethod
    async def stream_and_extract_files(
        cls,
        tarball_url: str,
        token: str,
    ) -> AsyncGenerator[StreamedFileEntry, None]:
        """Streams tarball via HTTP and yields text files incrementally."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        total_repo_bytes = 0

        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            async with client.stream("GET", tarball_url, headers=headers) as response:
                if response.status_code != 200:
                    raise ForgeAIException(
                        f"Failed to stream repository tarball ({response.status_code}): {response.reason_phrase}",
                        status_code=502,
                    )

                # GitHub returns a gzip tarball (.tar.gz). We read compressed chunks into a buffered stream
                # and unpack entries one-by-one.
                buffer = io.BytesIO()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    buffer.write(chunk)
                    total_repo_bytes += len(chunk)

                    if total_repo_bytes > settings.MAX_REPO_SIZE_BYTES:
                        raise ForgeAIException(
                            f"Repository size exceeded maximum configured limit of {settings.MAX_REPO_SIZE_BYTES // (1024 * 1024)} MB",
                            status_code=400,
                        )

                buffer.seek(0)

                try:
                    with tarfile.open(fileobj=buffer, mode="r:*") as tar:
                        for member in tar.getmembers():
                            if not member.isfile():
                                continue

                            # GitHub tarballs have a root directory like "owner-repo-sha/". Strip the first segment
                            path_parts = member.name.replace("\\", "/").split("/", 1)
                            if len(path_parts) < 2:
                                continue
                            relative_path = path_parts[1]

                            # Apply ignore filter before reading content
                            if IngestionFilter.should_ignore_path(relative_path):
                                continue

                            # Check individual file size limit
                            if not IngestionFilter.is_within_size_limit(member.size):
                                logger.info(
                                    f"Skipping oversized file: {relative_path} ({member.size} bytes)"
                                )
                                continue

                            f = tar.extractfile(member)
                            if f is None:
                                continue

                            file_bytes = f.read()

                            # Binary check
                            if IngestionFilter.is_binary_content(file_bytes):
                                continue

                            try:
                                text_content = file_bytes.decode("utf-8")
                            except UnicodeDecodeError:
                                continue

                            content_hash = hashlib.sha256(file_bytes).hexdigest()

                            yield StreamedFileEntry(
                                file_path=relative_path,
                                content=text_content,
                                content_hash=content_hash,
                                size_bytes=len(file_bytes),
                            )

                except tarfile.TarError as exc:
                    raise ForgeAIException(
                        f"Corrupted or invalid tarball archive: {str(exc)}", status_code=502
                    ) from exc
