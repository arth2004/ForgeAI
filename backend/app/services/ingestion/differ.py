from collections.abc import Mapping
from dataclasses import dataclass

from app.services.ingestion.tarball import StreamedFileEntry


@dataclass
class IndexDiffResult:
    added_files: list[StreamedFileEntry]
    modified_files: list[StreamedFileEntry]
    unchanged_files: list[StreamedFileEntry]
    deleted_paths: list[str]


class IndexDiffer:
    """Calculates file diffs between an active index and incoming commit entries."""

    @classmethod
    def calculate_diff(
        cls,
        existing_file_hashes: Mapping[str, str],
        incoming_entries: list[StreamedFileEntry],
    ) -> IndexDiffResult:
        added: list[StreamedFileEntry] = []
        modified: list[StreamedFileEntry] = []
        unchanged: list[StreamedFileEntry] = []
        seen_paths: set[str] = set()

        for entry in incoming_entries:
            seen_paths.add(entry.file_path)
            existing_hash = existing_file_hashes.get(entry.file_path)

            if existing_hash is None:
                added.append(entry)
            elif existing_hash != entry.content_hash:
                modified.append(entry)
            else:
                unchanged.append(entry)

        # Deleted paths are in existing index but not in incoming commit
        deleted_paths = [path for path in existing_file_hashes.keys() if path not in seen_paths]

        return IndexDiffResult(
            added_files=added,
            modified_files=modified,
            unchanged_files=unchanged,
            deleted_paths=deleted_paths,
        )
