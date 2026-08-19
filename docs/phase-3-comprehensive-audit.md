# Phase 3 Comprehensive Audit — Repository Intelligence Engine

**Audit Date:** 2026-08-19
**Auditor:** Automated Deep Audit (Antigravity)
**Scope:** Phase 3 as defined in `docs/roadmap.md`, validated against `architecture.md`, `decisions.md`, all backend/frontend code, Alembic migrations, Docker configuration, tests, and environment handling.
**Verdict:** Phase 3 is **substantially complete** with several **critical**, **major**, and **minor** deficiencies that must be addressed before a production release.

---

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Phase 3 Scope Verification](#2-phase-3-scope-verification)
3.  [Architecture Alignment](#3-architecture-alignment)
4.  [ADR Compliance](#4-adr-compliance)
5.  [Repository Connection](#5-repository-connection)
6.  [GitHub App Authentication](#6-github-app-authentication)
7.  [GitHub OAuth Flow](#7-github-oauth-flow)
8.  [GitHub Installation Association](#8-github-installation-association)
9.  [Repository Discovery](#9-repository-discovery)
10. [Branch Discovery](#10-branch-discovery)
11. [Repository Tarball Ingestion](#11-repository-tarball-ingestion)
12. [Streaming Ingestion](#12-streaming-ingestion)
13. [File Filtering](#13-file-filtering)
14. [SHA-256 Incremental Change Detection](#14-sha-256-incremental-change-detection)
15. [Tree-sitter AST Chunking](#15-tree-sitter-ast-chunking)
16. [Embedding Pipeline](#16-embedding-pipeline)
17. [Atomic Index Promotion](#17-atomic-index-promotion)
18. [Hybrid Retrieval Engine](#18-hybrid-retrieval-engine)
19. [API Endpoints & Schemas](#19-api-endpoints--schemas)
20. [Alembic Migrations](#20-alembic-migrations)
21. [Docker & Infrastructure](#21-docker--infrastructure)
22. [Test Coverage](#22-test-coverage)
23. [Frontend Integration](#23-frontend-integration)
24. [Security Assessment](#24-security-assessment)
25. [Phase 4 Leak Check](#25-phase-4-leak-check)
26. [Performance & Scalability Concerns](#26-performance--scalability-concerns)
27. [Bugs & Deficiencies Register](#27-bugs--deficiencies-register)
28. [Summary Verdict & Recommendations](#28-summary-verdict--recommendations)

---

## 1. Executive Summary

Phase 3 implements the Repository Intelligence Engine: a pipeline that connects to GitHub, streams repository archives, parses code into semantic AST chunks, generates embeddings via Gemini/OpenAI, stores them in pgvector with HNSW indexing, and exposes a 3-stage hybrid retrieval endpoint fusing dense vector, sparse full-text (GIN tsvector), and exact symbol matching via Reciprocal Rank Fusion (RRF k=60).

**Overall Assessment:**

| Dimension | Rating | Notes |
|---|---|---|
| Feature Completeness | ✅ ~92% | All 14 core capabilities are implemented. Missing: VALIDATED intermediate state, proper ARQ dispatch, webhook-driven re-index. |
| Architecture Alignment | ✅ ~90% | Follows ADRs closely. Minor deviations noted. |
| Code Quality | ⚠️ ~80% | Solid patterns but several production concerns (fire-and-forget tasks, hardcoded dimension, embedding copy overhead). |
| Security | ⚠️ ~85% | Tokens are ephemeral; PEM excluded from git. Some frontend token-scanning behavior is overly broad. |
| Test Coverage | ✅ ~88% | 58/58 passing. Strong integration coverage. Gaps in retrieval ranking quality benchmarks and large-repo stress tests. |
| Production Readiness | ⚠️ ~75% | Several critical items must be fixed before production deployment. |

---

## 2. Phase 3 Scope Verification

Verified against `docs/roadmap.md` Phase 3 requirements:

| Requirement | Status | Location |
|---|---|---|
| A. Repository connection | ✅ Implemented | [github.py](file:///c:/Users/artha/ForgeAi/backend/app/api/v1/github.py), [client.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/client.py) |
| B. GitHub App authentication (RS256 JWT) | ✅ Implemented | [client.py#L50-L65](file:///c:/Users/artha/ForgeAi/backend/app/services/github/client.py#L50-L65) |
| C. GitHub OAuth flow | ✅ Implemented | [auth.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/auth.py), [github.py#L47-L81](file:///c:/Users/artha/ForgeAi/backend/app/api/v1/github.py#L47-L81) |
| D. GitHub installation association | ✅ Implemented | [auth.py#L120-L222](file:///c:/Users/artha/ForgeAi/backend/app/services/github/auth.py#L120-L222) |
| E. Repository discovery | ✅ Implemented | [repositories.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/repositories.py) |
| F. Branch discovery | ✅ Implemented | [branches.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/branches.py) |
| G. Repository tarball ingestion | ✅ Implemented | [tarball.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/tarball.py) |
| H. Streaming ingestion | ✅ Implemented | [tarball.py#L25-L117](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/tarball.py#L25-L117) |
| I. File filtering | ✅ Implemented | [filters.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/filters.py) |
| J. SHA-256 incremental change detection | ✅ Implemented | [differ.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/differ.py) |
| K. Tree-sitter AST chunking | ✅ Implemented | [chunker.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/chunker.py), [symbols.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/symbols.py), [languages.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/languages.py) |
| L. Embedding pipeline (Gemini + OpenAI) | ✅ Implemented | [gemini.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/gemini.py), [openai.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/openai.py), [factory.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/factory.py) |
| M. Atomic index version promotion | ⚠️ Partial | [engine.py#L364-L400](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py#L364-L400) — skips VALIDATED intermediate |
| N. 3-stage hybrid retrieval + RRF | ✅ Implemented | [hybrid.py](file:///c:/Users/artha/ForgeAi/backend/app/services/retrieval/hybrid.py) |

---

## 3. Architecture Alignment

### Verified Against `architecture.md`

| Architectural Requirement | Status | Notes |
|---|---|---|
| PostgreSQL 16 + pgvector + HNSW | ✅ | Docker uses `pgvector/pgvector:pg16`, migration creates HNSW index with `m=16, ef_construction=64` |
| Redis + ARQ worker queue | ⚠️ Partial | ARQ worker is configured ([workers/main.py](file:///c:/Users/artha/ForgeAi/backend/app/workers/main.py)), but API endpoint uses `asyncio.create_task()` instead of ARQ enqueue |
| tsvector GIN full-text index | ✅ | Migration `0004` creates `GENERATED ALWAYS AS` stored tsvector with weighted A/B/C zones |
| gemini-embedding-2 (768d) | ✅ | Hardcoded in `GeminiEmbeddingProvider`, configurable via `settings.GEMINI_EMBEDDING_DIMENSION` |
| Streaming tarball HTTP extraction | ✅ | `StreamingTarballProcessor` uses `httpx.AsyncClient.stream()` with `Follow-Redirects` |
| Zero persistent tokens | ✅ | No OAuth tokens or installation tokens are written to the database |
| Multi-tenant isolation | ✅ | `verify_project_access()` checks org membership before any indexing/search operation |

### Deviations Detected

> [!WARNING]
> **DEV-1: `asyncio.create_task()` instead of ARQ enqueue in API**
> In [ingestion.py#L105](file:///c:/Users/artha/ForgeAi/backend/app/api/v1/ingestion.py#L105), indexing is dispatched via `asyncio.create_task(IngestionEngine.run_indexing(...))` — a fire-and-forget pattern that:
> - Loses the task reference (no `await`, no cancellation)
> - Fails silently if the API process restarts or the task raises an unhandled exception
> - Bypasses the ARQ worker queue entirely, despite ARQ being configured in `workers/main.py`
>
> **Severity: CRITICAL for production**

> [!WARNING]
> **DEV-2: Missing VALIDATED intermediate state**
> `architecture.md` specifies the promotion flow: `BUILDING → VALIDATED → ACTIVE`. The actual code in [engine.py#L376-L378](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py#L376-L378) promotes directly `BUILDING → ACTIVE`, skipping the `VALIDATED` state entirely. While `IndexVersionStatus` enum defines a `VALIDATED` variant in the model, it's never used in the engine.
>
> **Severity: MAJOR** — Validation is performed (chunk-embedding count match at L358), but there's no durable VALIDATED state between the integrity check and promotion.

---

## 4. ADR Compliance

| ADR | Decision | Status | Notes |
|---|---|---|---|
| ADR-001: Python/FastAPI + Next.js | Python backend, Next.js frontend | ✅ | |
| ADR-003: JWT HS256 auth | HS256 with configurable secret | ✅ | |
| ADR-005: pgvector HNSW | Vector(768), cosine_distance, m=16, ef=64 | ✅ | |
| ADR-006: Tree-sitter AST | Python, TS/JS, Markdown, JSON, YAML parsers | ✅ | |
| ADR-007: Streaming tarball | httpx async streaming with content hash | ✅ | |
| ADR-008: tsvector GIN full-text | Weighted A/B/C zones on symbol/header/content | ✅ | |
| ADR-009: Hybrid RRF k=60 | 3-stage fusion with configurable weights | ✅ | Default k=60 confirmed at [hybrid.py#L164](file:///c:/Users/artha/ForgeAi/backend/app/services/retrieval/hybrid.py#L164) |
| ADR-010: Atomic version promotion | BUILDING→ACTIVE with integrity check | ⚠️ | Missing VALIDATED intermediate (see DEV-2) |
| ADR-011: Gemini quota handling | Daily quota detection, graceful failure | ✅ | |
| ADR-012: GitHub App architecture | RS256 JWT, ephemeral tokens, installation ownership | ✅ | |

---

## 5. Repository Connection

**File:** [github.py#L162-L241](file:///c:/Users/artha/ForgeAi/backend/app/api/v1/github.py#L162-L241)

✅ **Complete.** The `POST /github/projects/create-from-repo` endpoint atomically creates:
1. A `Project` record
2. A `Repository` record with `github_repo_id`, `owner`, `full_name`, `default_branch`, `html_url`
3. A `RepositoryBranch` with `latest_commit_sha`

Rich metadata fields (`description`, `language`, `is_private`, `html_url`) are persisted.

---

## 6. GitHub App Authentication

**File:** [client.py#L50-L65](file:///c:/Users/artha/ForgeAi/backend/app/services/github/client.py#L50-L65)

✅ **Complete.** RS256 JWT generation:
- `iat` with 60-second clock skew allowance
- `exp` at 9 minutes (within GitHub's 10-minute maximum)
- `iss` set to `GITHUB_APP_ID`
- Private key loaded from `GITHUB_PRIVATE_KEY` env var or `GITHUB_PRIVATE_KEY_PATH` file
- Backslash-n unescaping for containerized environments

---

## 7. GitHub OAuth Flow

**File:** [auth.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/auth.py)

✅ **Complete.** HMAC-SHA256 signed state parameter with:
- 10-minute expiry (`STATE_EXPIRY_SECONDS = 600`)
- UUID nonce for replay protection
- `hmac.compare_digest()` for constant-time signature comparison
- Code-for-token exchange via `https://github.com/login/oauth/access_token`
- Token used only within callback lifecycle and never persisted

---

## 8. GitHub Installation Association

**File:** [auth.py#L120-L222](file:///c:/Users/artha/ForgeAi/backend/app/services/github/auth.py#L120-L222)

✅ **Complete.** Installation ownership verification:
1. Fetches user installations via OAuth user token
2. Validates redirect-provided `installation_id` against user's installation list
3. Falls back to App JWT verification of installation account metadata
4. Auto-assigns first authorized installation if none specified
5. Rejects installations that don't belong to the authenticated GitHub identity

---

## 9. Repository Discovery

**File:** [repositories.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/repositories.py)

✅ **Complete.** Paginated discovery via `GET /installation/repositories` with installation access token. Returns formatted metadata including `github_repo_id`, `full_name`, `owner`, `is_private`, `default_branch`, `html_url`, `description`, `language`.

---

## 10. Branch Discovery

**File:** [branches.py](file:///c:/Users/artha/ForgeAi/backend/app/services/github/branches.py)

✅ **Complete.** Lists branches via `GET /repos/{owner}/{repo}/branches` with proper `default_branch` flag and `is_protected` status.

---

## 11. Repository Tarball Ingestion

**File:** [tarball.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/tarball.py)

✅ **Complete.** Key characteristics:
- URL pattern: `https://api.github.com/repos/{owner}/{repo}/tarball/{commit_sha}`
- Authorization via `Bearer` installation access token
- `follow_redirects=True` for GitHub's S3 redirect
- Total size guard: `MAX_REPO_SIZE_BYTES` (500 MB default)
- Individual file guard: `MAX_FILE_SIZE_BYTES` (1 MB default)
- Binary file detection and skip
- UTF-8 decode with `errors="replace"` for resilience
- SHA-256 content hash computed during streaming

---

## 12. Streaming Ingestion

**File:** [tarball.py#L28-L117](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/tarball.py#L28-L117)

✅ **Implemented** but with a caveat:

> [!NOTE]
> The streaming is "semi-streaming": the tarball bytes are accumulated in an `io.BytesIO` buffer via `async for chunk in response.aiter_bytes()` before being processed by `tarfile.open(fileobj=buffer, mode='r:gz')`. This is because Python's `tarfile` requires a seekable file-like object.
>
> For repositories under 500 MB this is acceptable, but for truly large repositories the full tarball will be buffered in RAM. The architecture states "streaming HTTP extraction" — the HTTP transfer IS streamed, but the tarball decompression is not truly file-by-file streaming.
>
> **Severity: MINOR** — The 500 MB limit mitigates OOM risk.

---

## 13. File Filtering

**File:** [filters.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/filters.py)

✅ **Complete.** Exclusion rules include:
- Directories: `node_modules`, `.git`, `__pycache__`, `vendor`, `dist`, `build`, `.next`, etc.
- Extensions: `.pyc`, `.exe`, `.dll`, `.so`, `.bin`, `.wasm`, `.lock`, etc.
- Size guard delegated to tarball processor
- Called during tarball extraction before content hashing

---

## 14. SHA-256 Incremental Change Detection

**File:** [differ.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/differ.py)

✅ **Complete.** `IndexDiffer.calculate_diff()`:
- Compares incoming `StreamedFileEntry.content_hash` against stored `RepositoryFile.content_hash`
- Produces `IndexDiffResult` with `added_files`, `modified_files`, `unchanged_files`, `deleted_files`
- Only added/modified files are re-parsed and re-embedded
- Unchanged files/chunks/embeddings are shallow-copied to the new index version

---

## 15. Tree-sitter AST Chunking

**Files:**
- [chunker.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/chunker.py)
- [symbols.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/symbols.py)
- [languages.py](file:///c:/Users/artha/ForgeAi/backend/app/services/parser/languages.py)

✅ **Complete.** Supports 6 language grammars:
- **Python** (`tree-sitter-python`) — functions, classes, methods, decorators
- **TypeScript** (`tree-sitter-typescript`) — functions, classes, interfaces, type aliases, enums
- **JavaScript** (`tree-sitter-javascript`) — functions, classes, methods, arrow functions
- **Markdown** (`tree-sitter-markdown`) — section-based heading chunking
- **JSON** (`tree-sitter-json`) — top-level key chunking
- **YAML** (`tree-sitter-yaml`) — block mapping chunking

Fallback: Line-based sliding window chunking for unrecognized languages.

`ChunkType` enum: `FUNCTION`, `CLASS`, `METHOD`, `INTERFACE`, `MODULE`, `BLOCK`, `IMPORT`, `SECTION`.

`context_header` generates breadcrumb-style headers (e.g., `# class ProjectService > method create > file: project_service.py`).

---

## 16. Embedding Pipeline

**Files:**
- [base.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/base.py) — ABC with `embed_documents()`, `embed_query()`, `provider_name`, `model_name`, `dimension`, `version`
- [gemini.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/gemini.py) — Primary provider
- [openai.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/openai.py) — Fallback provider
- [factory.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/factory.py) — Factory pattern

✅ **Complete** with robust features:
- Sub-batch processing (`MAX_CHUNKS_PER_EMBED_BATCH`, default 100)
- Exponential backoff with jitter for transient 429/5xx errors
- `Retry-After` header parsing and `RetryInfo` detail extraction
- Daily/project quota exhaustion detection → immediate `EmbeddingQuotaExhaustedException` (no wasteful retries)
- API key sanitization in error messages via `sanitize_error()`
- Gemini uses `RETRIEVAL_DOCUMENT` task type for documents, `RETRIEVAL_QUERY` for queries
- `outputDimensionality: 768` enforced in API payload

> [!WARNING]
> **OpenAI provider does NOT pass `dimensions` in the API request** ([openai.py#L86-L89](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/openai.py#L86-L89)). For `text-embedding-3-small` (1536d default), this means OpenAI embeddings would be 1536-dimensional while the pgvector column is `Vector(768)`. This would cause a runtime crash if the OpenAI provider is selected.
>
> **Severity: MAJOR** — Must add `dimensions: self._dimension` to OpenAI payload.

---

## 17. Atomic Index Promotion

**File:** [engine.py#L364-L400](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py#L364-L400)

⚠️ **Implemented with deviations:**

✅ Correct behaviors:
- Creates `BUILDING` version
- Validates integrity (chunk count = embedding count, L348-362)
- Atomically marks old `ACTIVE` → `SUPERSEDED` and new → `ACTIVE` in single transaction
- On failure: marks version `FAILED`, preserves previous `ACTIVE` index
- Updates `Repository.indexing_status` and `RepositoryBranch.latest_commit_sha`
- Quota exhaustion failures get user-friendly error messages

⚠️ Deviations:
1. **Missing `VALIDATED` state** — Promotion goes `BUILDING → ACTIVE` directly (DEV-2)
2. **No old version cleanup** — `SUPERSEDED` versions are never cleaned up. Over time this will accumulate stale data.

---

## 18. Hybrid Retrieval Engine

**File:** [hybrid.py](file:///c:/Users/artha/ForgeAi/backend/app/services/retrieval/hybrid.py)

✅ **Complete.** 3-stage pipeline with RRF fusion:

### Stage 1: Dense Vector Search (pgvector HNSW)
- Embeds query via `embed_query()` with `RETRIEVAL_QUERY` task type
- Uses `ChunkEmbedding.embedding.cosine_distance(query_vector)` for PostgreSQL
- SQLite fallback with pure-Python `python_cosine_distance()`
- Top 60 candidates

### Stage 2: Sparse Full-Text Search (GIN tsvector)
- `ts_rank_cd()` with `plainto_tsquery('english', query)` on `search_vector`
- `@@` operator for filtering
- SQLite fallback with naive term-in-text matching
- Top 60 candidates

### Stage 3: Exact Symbol & Path Matching
- `STEM_SYNONYMS` expansion (e.g., "authentication" → "auth", "login", "jwt", "oauth")
- Weighted scoring: symbol exact match (150), symbol contains (40), filename match (120), path directory (70), generic path (25)
- `GENERIC_FILENAMES` filtering to avoid over-boosting common names like `index`, `main`, `utils`
- Top 60 candidates

### RRF Fusion
- Formula: `score = Σ weight_i / (k + rank_i)` with k=60
- Configurable weights: `dense=1.0, sparse=0.8, symbol=1.6`
- **Code Entity Intent Weighting**: Implementation queries boost code AST chunks by 1.35x and demote non-code by 0.85x
- Result includes commit lineage (`commit_sha`, `branch_name`, `index_version_id`)

> [!NOTE]
> **BM25 labeling inaccuracy**: The frontend [RetrievalSandbox.tsx:72](file:///c:/Users/artha/ForgeAi/frontend/src/components/indexing/RetrievalSandbox.tsx#L72) mentions "GIN full-text BM25 search" but PostgreSQL's `ts_rank_cd` uses a cover density ranking algorithm, not BM25. This is a cosmetic/documentation issue only.

---

## 19. API Endpoints & Schemas

### Phase 3 Endpoints

| Method | Path | Schema | Status |
|---|---|---|---|
| POST | `/projects/{pid}/repositories/{rid}/index` | `TriggerIndexingRequest` → `IndexingJobResponse` | ✅ |
| GET | `/projects/{pid}/repositories/{rid}/index/status` | → `IndexingJobResponse` | ✅ |
| POST | `/projects/{pid}/search/hybrid` | `HybridSearchRequest` → `HybridSearchResponse` | ✅ |
| GET | `/projects/{pid}/files` | → `RepositoryFileResponse[]` | ✅ |
| GET | `/projects/{pid}/files/{fid}` | → `RepositoryFileDetailResponse` | ✅ |

### Pydantic Schemas

**File:** [ingestion.py](file:///c:/Users/artha/ForgeAi/backend/app/schemas/ingestion.py)

✅ Complete with:
- `HybridSearchRequest` validates `query` (1-1000 chars), `top_k` (1-100)
- `EvidenceChunkResponse` includes all RRF diagnostics (`dense_rank`, `sparse_rank`, `symbol_rank`, `rrf_score`)
- `IndexingJobResponse` includes progress telemetry (`total_files`, `processed_files`, `total_chunks`, `embedded_chunks`, `error_message`)

---

## 20. Alembic Migrations

**File:** [0004_repo_intelligence.py](file:///c:/Users/artha/ForgeAi/backend/alembic/versions/0004_repo_intelligence.py)

✅ **Complete.** Creates all Phase 3 tables:

| Table | Key Columns | Indexes | Constraints |
|---|---|---|---|
| `repository_index_versions` | id, repository_id, branch_id, commit_sha, status, total_files, total_chunks | repository_id, branch_id, status | FK→repositories, FK→repository_branches (CASCADE) |
| `repository_files` | id, index_version_id, file_path, file_name, extension, language, size_bytes, content_hash | index_version_id, repository_id, content_hash | FK→repository_index_versions (CASCADE), UQ(index_version_id, file_path) |
| `code_chunks` | id, index_version_id, file_id, chunk_type, symbol_name, content, context_header, search_vector (GENERATED) | index_version_id, file_id, repository_id, symbol_name, search_vector (GIN) | FK cascades |
| `chunk_embeddings` | id, chunk_id, index_version_id, provider, model, dimension, embedding Vector(768) | index_version_id, repository_id, HNSW (vector_cosine_ops m=16 ef=64) | FK cascades, UQ(chunk_id, provider, model, embedding_version) |
| `code_dependencies` | id, index_version_id, file_id, source_symbol, target_symbol, imported_path, dependency_type | index_version_id, imported_path | FK cascades |
| `indexing_jobs` | id, repository_id, branch_id, index_version_id, commit_sha, status, progress fields, error_message | repository_id, status | FK→repositories (CASCADE), FK→index_versions (SET NULL) |

Key observations:
- ✅ `pgvector` extension created: `CREATE EXTENSION IF NOT EXISTS vector`
- ✅ `search_vector` is `GENERATED ALWAYS AS ... STORED` with weighted zones
- ✅ HNSW index with correct parameters for cosine distance
- ✅ Migration chain: `0003_drop_github_token` → `0004_repo_intelligence`
- ✅ Clean `downgrade()` drops tables in reverse dependency order

---

## 21. Docker & Infrastructure

**File:** [docker-compose.yml](file:///c:/Users/artha/ForgeAi/docker-compose.yml)

| Service | Image | Status | Notes |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | ✅ | Correct image for pgvector + PostgreSQL 16 |
| `redis` | `redis:7-alpine` | ✅ | For ARQ and rate limiting |
| `api` | `./backend (Dockerfile)` | ✅ | Runs `alembic upgrade head && uvicorn` |
| `worker` | `./backend (Dockerfile)` | ✅ | Runs `python -m arq app.workers.main.WorkerSettings` |
| `frontend` | `./frontend (Dockerfile)` | ✅ | Next.js with `NEXT_PUBLIC_API_URL` |

- ✅ Health checks on postgres (`pg_isready`) and redis (`redis-cli ping`)
- ✅ Service dependency ordering with `condition: service_healthy`
- ✅ Internal network for service communication (`forgeai-network`)
- ✅ Persistent volumes for postgres and redis data
- ✅ Environment variables properly injected from `.env`

> [!WARNING]
> **Worker container is configured but API bypasses it.** The `worker` service correctly runs ARQ with `index_repository_task` registered, but the API dispatches indexing via `asyncio.create_task()` instead of enqueuing to ARQ. This means the `worker` container sits idle in Docker Compose while the `api` container runs indexing inline.

---

## 22. Test Coverage

**All 58 tests pass** (`58 passed in 13.27s`).

### Phase 3 Specific Tests

| Test File | Tests | Coverage Area |
|---|---|---|
| `integration/test_incremental_indexing.py` | 3 | Full + incremental workflow, failed indexing retention, quota exhaustion |
| `integration/test_ingestion_api.py` | 5 | Trigger, status, hybrid search, file listing, tenant isolation |
| `integration/test_retrieval_integration.py` | 1 | End-to-end hybrid search ranking |
| `integration/test_github_api.py` | 9 | OAuth, callback, repositories, branches, project creation, disconnect |
| `unit/test_embedding_provider.py` | 7 | Factory, batching, query embed, 429 retry, quota detection, sanitization |
| `unit/test_tree_sitter_parsers.py` | 5 | Language detection, Python/TS/MD/JSON/YAML AST parsing |
| `unit/test_ingestion_differ.py` | 2 | Filters and diff calculations |
| `unit/test_retrieval_ranking.py` | 3 | Term extraction, implementation query detection, cosine distance |
| `unit/test_github_auth.py` | 4 | State generation, validation, tampering, expiry |
| `unit/test_github_client.py` | 3 | JWT generation, installation token scoping, rate limit handling |

### Test Gaps

> [!IMPORTANT]
> 1. **No retrieval quality/ranking benchmark** — Tests verify that search returns results but don't validate that the correct function/class appears in the top-K for specific queries.
> 2. **No large-repository stress test** — All tests use small synthetic data (3-10 files). No verification that ingestion handles 500+ files gracefully.
> 3. **No concurrent indexing test** — What happens if two indexing jobs target the same branch simultaneously?
> 4. **No OpenAI provider integration test** — Only Gemini provider is tested via mocking.
> 5. **No ARQ worker dispatch test** — Tests call `IngestionEngine.run_indexing()` directly, never through ARQ.

---

## 23. Frontend Integration

### Phase 3 Frontend Components

| Component | File | Status |
|---|---|---|
| Index Status Card | [IndexStatusCard.tsx](file:///c:/Users/artha/ForgeAi/frontend/src/components/indexing/IndexStatusCard.tsx) | ✅ |
| Retrieval Sandbox | [RetrievalSandbox.tsx](file:///c:/Users/artha/ForgeAi/frontend/src/components/indexing/RetrievalSandbox.tsx) | ✅ |
| File Explorer Tree | [FileExplorerTree.tsx](file:///c:/Users/artha/ForgeAi/frontend/src/components/indexing/FileExplorerTree.tsx) | ✅ |
| Project Workspace Page | [page.tsx](file:///c:/Users/artha/ForgeAi/frontend/src/app/(dashboard)/projects/[id]/page.tsx) | ✅ |

**Key UI capabilities:**
- ✅ Index trigger with incremental/full re-index modal
- ✅ Real-time polling (2.5s interval) during indexing
- ✅ Progress metrics: files, chunks, vectors, commit SHA
- ✅ Error notification display
- ✅ Hybrid search sandbox with sample queries
- ✅ Result cards with RRF scores, dense/sparse/symbol rank badges
- ✅ Collapsible code preview with context headers
- ✅ Commit lineage and branch info
- ✅ File explorer with chunk counts
- ✅ Tab-based navigation (Overview / Retrieval / Files)

### Frontend API Client

**File:** [api-client.ts](file:///c:/Users/artha/ForgeAi/frontend/src/lib/api-client.ts)

Phase 3 methods:
- `triggerIndexing(projectId, repoId, isFullReindex, branchId)`
- `getIndexingStatus(projectId, repoId)`
- `searchHybrid(projectId, query, branchId, topK)`
- `listIndexedFiles(projectId, branchId)`
- `getFileDetail(projectId, fileId)`

> [!WARNING]
> **Overly broad token scanning** ([api-client.ts#L84-L146](file:///c:/Users/artha/ForgeAi/frontend/src/lib/api-client.ts#L84-L146)): The `getToken()` method scans ALL localStorage and sessionStorage keys looking for anything that could be a JWT. While this handles edge cases of token storage inconsistency, it could inadvertently pick up tokens from unrelated applications sharing the same origin, creating a security concern.

---

## 24. Security Assessment

| Check | Status | Notes |
|---|---|---|
| OAuth tokens persisted to DB | ✅ Safe | Never written to PostgreSQL |
| Installation tokens persisted | ✅ Safe | In-memory only with 50-min TTL, 5-min safety buffer |
| PEM file in git | ✅ Safe | `.gitignore` includes `*.pem` |
| API key sanitization | ✅ | `sanitize_error()` redacts keys in error messages |
| CSRF protection (OAuth) | ✅ | HMAC-SHA256 signed state with expiry |
| Timing-safe comparison | ✅ | `hmac.compare_digest()` used |
| Multi-tenant isolation | ✅ | All search/indexing APIs verify org membership |
| SQL injection risk | ✅ Safe | All queries use parameterized SQLAlchemy |
| JWT secret strength | ⚠️ | Default is a readable string, not cryptographically random. Documented as "change in production". |
| Encryption key | ⚠️ | Default is a sequential hex string. Documented as needing change. |

---

## 25. Phase 4 Leak Check

✅ **No Phase 4 leaks detected.**

- No `LangGraph` imports or references in backend or frontend code
- No `MCP` (Model Context Protocol) references in application code
- No `langchain` or `langgraph` dependencies in `pyproject.toml`
- No `Supabase` references anywhere in the codebase
- All imports are within Phase 1-3 scope

---

## 26. Performance & Scalability Concerns

| Concern | Severity | Description |
|---|---|---|
| Embedding copy overhead | **MAJOR** | Incremental indexing copies ALL chunks + embeddings for unchanged files by creating new DB rows ([engine.py#L259-L302](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py#L259-L302)). For a 1000-file repo where 5 files changed, this copies ~995 files × N chunks × embeddings. Should use a reference-based approach instead. |
| `SELECT ... IN (many_ids)` | **MINOR** | [hybrid.py#L454](file:///c:/Users/artha/ForgeAi/backend/app/services/retrieval/hybrid.py#L454) passes all candidate chunk IDs via `CodeChunk.id.in_(sorted_chunk_ids)`. For small result sets (≤15) this is fine, but if `all_chunk_ids` grows large (union of 3×60=180 max), this could be slow without an index. |
| Total chunks count query | **MINOR** | [engine.py#L305-L309](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py#L305-L309) counts chunks by loading all scalars: `len(total_chunks_res.scalars().all())`. Should use `select(func.count(CodeChunk.id))` instead. |
| httpx client per-request | **MINOR** | Both embedding providers create a new `httpx.AsyncClient` for every batch request. Should use a shared client with connection pooling. |
| `SUPERSEDED` cleanup | **MAJOR** | Old `SUPERSEDED` index versions are never cleaned up. After many re-indexes, the database will accumulate large amounts of stale data. |

---

## 27. Bugs & Deficiencies Register

### Critical

| # | Category | Description | File | Line(s) |
|---|---|---|---|---|
| C-1 | Architecture | `asyncio.create_task()` fire-and-forget instead of ARQ enqueue | [ingestion.py](file:///c:/Users/artha/ForgeAi/backend/app/api/v1/ingestion.py) | 103-112 |

### Major

| # | Category | Description | File | Line(s) |
|---|---|---|---|---|
| M-1 | Architecture | Missing VALIDATED intermediate state in promotion flow | [engine.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py) | 376-378 |
| M-2 | Embedding | OpenAI provider doesn't pass `dimensions` param → Vector(768) mismatch crash | [openai.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/openai.py) | 86-89 |
| M-3 | Performance | Unchanged file/chunk/embedding copy creates duplicate rows instead of references | [engine.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py) | 259-302 |
| M-4 | Operations | No SUPERSEDED version cleanup (stale data accumulation) | [engine.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py) | N/A |

### Minor

| # | Category | Description | File | Line(s) |
|---|---|---|---|---|
| m-1 | Documentation | Frontend references "BM25" but PostgreSQL uses `ts_rank_cd` (cover density) | [RetrievalSandbox.tsx](file:///c:/Users/artha/ForgeAi/frontend/src/components/indexing/RetrievalSandbox.tsx) | 72 |
| m-2 | Performance | Chunk count uses `len(scalars().all())` instead of SQL `COUNT()` | [engine.py](file:///c:/Users/artha/ForgeAi/backend/app/services/ingestion/engine.py) | 305-309, 355-356 |
| m-3 | Performance | Per-request `httpx.AsyncClient` creation instead of shared pool | [gemini.py](file:///c:/Users/artha/ForgeAi/backend/app/services/embedding/gemini.py) | 198 |
| m-4 | Code Quality | `norm_a` computed incorrectly in `python_cosine_distance` (uses `zip(vec_a, vec_b)` but only accesses `a`) | [hybrid.py](file:///c:/Users/artha/ForgeAi/backend/app/services/retrieval/hybrid.py) | 123-124 |
| m-5 | Security | Overly broad localStorage/sessionStorage token scanning | [api-client.ts](file:///c:/Users/artha/ForgeAi/frontend/src/lib/api-client.ts) | 84-146 |
| m-6 | Testing | No retrieval quality benchmark tests | tests/ | N/A |
| m-7 | Testing | No concurrent indexing test | tests/ | N/A |
| m-8 | Operations | `job_timeout=600` (10 min) in ARQ may be insufficient for large repos | [main.py](file:///c:/Users/artha/ForgeAi/backend/app/workers/main.py) | 30 |
| m-9 | Deprecation | 73 `datetime.utcnow()` deprecation warnings in test output | models/ | Various |

---

## 28. Summary Verdict & Recommendations

### Verdict: **Phase 3 is functionally complete but NOT production-ready**

The Repository Intelligence Engine is well-architected and covers all 14 core requirements. The ingestion pipeline, AST chunking, embedding generation, and hybrid retrieval are all correctly implemented and pass comprehensive tests. However, several issues prevent a production release:

### Must-Fix Before Production (P0)

1. **Route indexing through ARQ** — Replace `asyncio.create_task()` in `ingestion.py` with proper ARQ job enqueue via Redis. This ensures job durability, crash recovery, and worker scaling.

2. **Fix OpenAI embedding dimensions** — Add `dimensions: self._dimension` to the OpenAI API payload. Without this, switching to OpenAI will crash with a Vector(768) column mismatch.

3. **Add SUPERSEDED cleanup** — Implement a background task or post-promotion hook that deletes `SUPERSEDED` index versions (and their cascaded files/chunks/embeddings) after a configurable retention period.

### Should-Fix (P1)

4. **Implement VALIDATED intermediate state** — Add a brief `VALIDATED` state between integrity check and `ACTIVE` promotion per the architecture spec.

5. **Optimize incremental indexing** — Replace row-copy of unchanged files with a reference-based approach (e.g., shared file/chunk IDs across versions, or a version-to-file junction table).

6. **Use `func.count()` instead of `len(scalars().all())`** — Minor performance fix in engine.py.

7. **Share httpx client** — Use a module-level or class-level `httpx.AsyncClient` with connection pooling.

### Nice-to-Have (P2)

8. **Add retrieval quality benchmarks** — Create a test fixture with known code and verify top-K ranking accuracy.
9. **Add concurrent indexing guard** — Prevent two simultaneous indexing jobs on the same branch.
10. **Fix `datetime.utcnow()` deprecation** — Replace with `datetime.now(UTC)` throughout.
11. **Narrow frontend token scanning** — Restrict to `forgeai_token` key only.
12. **Fix BM25 label** — Update frontend text to "GIN full-text" or "tsvector cover density".
