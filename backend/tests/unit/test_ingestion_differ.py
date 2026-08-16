from app.services.ingestion.differ import IndexDiffer
from app.services.ingestion.filters import IngestionFilter
from app.services.ingestion.tarball import StreamedFileEntry


def test_ingestion_filters():
    # Should ignore
    assert IngestionFilter.should_ignore_path("node_modules/express/index.js") is True
    assert IngestionFilter.should_ignore_path(".git/config") is True
    assert IngestionFilter.should_ignore_path(".github/workflows/ci.yml") is True
    assert IngestionFilter.should_ignore_path("dist/bundle.js") is True
    assert IngestionFilter.should_ignore_path("package-lock.json") is True
    assert IngestionFilter.should_ignore_path("assets/logo.png") is True
    assert IngestionFilter.should_ignore_path("static/app.min.js") is True

    # Should NOT ignore
    assert IngestionFilter.should_ignore_path("src/index.ts") is False
    assert IngestionFilter.should_ignore_path("backend/app/main.py") is False
    assert IngestionFilter.should_ignore_path("docs/architecture.md") is False
    assert IngestionFilter.should_ignore_path("docker-compose.yml") is False


def test_index_differ_calculations():
    existing_hashes = {
        "src/auth.ts": "hash_auth_v1",
        "src/user.ts": "hash_user_v1",
        "src/deleted.ts": "hash_deleted_v1",
    }

    incoming_entries = [
        # Unchanged
        StreamedFileEntry(
            file_path="src/auth.ts",
            content="...",
            content_hash="hash_auth_v1",
            size_bytes=100,
        ),
        # Modified
        StreamedFileEntry(
            file_path="src/user.ts",
            content="...",
            content_hash="hash_user_v2",
            size_bytes=150,
        ),
        # Added
        StreamedFileEntry(
            file_path="src/project.ts",
            content="...",
            content_hash="hash_project_v1",
            size_bytes=200,
        ),
    ]

    diff = IndexDiffer.calculate_diff(existing_hashes, incoming_entries)

    assert len(diff.added_files) == 1
    assert diff.added_files[0].file_path == "src/project.ts"

    assert len(diff.modified_files) == 1
    assert diff.modified_files[0].file_path == "src/user.ts"

    assert len(diff.unchanged_files) == 1
    assert diff.unchanged_files[0].file_path == "src/auth.ts"

    assert len(diff.deleted_paths) == 1
    assert diff.deleted_paths[0] == "src/deleted.ts"
