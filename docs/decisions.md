# Forge AI — Architecture Decision Records (ADRs)

## ADR-001: Monorepo Architecture

### Status
Accepted

### Context
Forge AI consists of a Next.js frontend, a FastAPI backend with background workers, shared documentation, Docker orchestration, and shared configuration files. We need a development and deployment strategy that simplifies developer onboarding, cross-boundary type definitions, and continuous integration.

### Decision
We will use a **Monorepo** structure (`frontend/`, `backend/`, `docs/`, `.github/`).

### Consequences
- **Positive**: Single pull request for end-to-end features spanning frontend and backend; unified CI/CD workflow; easier local Docker Compose setup; single repository for portfolio demonstration.
- **Negative**: Requires clean directory boundaries and independent dependency management (`package.json` for frontend, `pyproject.toml` for backend).

---

## ADR-002: PostgreSQL + pgvector for Unified Persistence & Vector Search

### Status
Accepted

### Context
Codebase understanding requires approximate nearest-neighbor vector similarity search alongside complex relational metadata (Organizations, Projects, Repositories, Files, Line numbers, Permissions, Conversations, Citations).

### Decision
We will use **PostgreSQL 16 with the `pgvector` extension** as our single persistence and vector database layer. HNSW (Hierarchical Navigable Small World) indexing is selected for efficient approximate nearest-neighbor search.

### Consequences
- **Positive**:
  - ACID guarantees and transactional consistency between code chunks, metadata, and vectors.
  - Eliminates dual-write synchronization issues between relational databases and external vector DBs.
  - Zero added external infrastructure dependencies or cloud SaaS vector costs.
  - Unified backup and point-in-time recovery.
  - Production retrieval latency will be continuously benchmarked against dataset scale.
- **Negative**:
  - Requires maintaining PostgreSQL pgvector extension in Docker and production hosting.

---

## ADR-003: LangGraph for Incremental Agentic Orchestration

### Status
Accepted

### Context
Repository-level software engineering tasks require multi-step reasoning, state persistence, conditional branching, and verification loops. Linear chains or single LLM calls cannot reliably verify whether retrieved evidence is sufficient before answering.

### Decision
We will use **LangGraph** to model our agent workflows. We will begin with a single, robust **Project Assistant** graph (`Query Understanding -> Retrieval -> Evidence Analysis -> Verification -> Response Synthesis + Citations`). Specialized agents (Code Review, Documentation, Architecture, Test Generation) will be introduced in subsequent phases.

### Consequences
- **Positive**:
  - Explicit, inspectable state transitions at every step.
  - Clean separation between evidence retrieval, fact verification, and response synthesis.
  - Avoids premature multi-agent complexity while establishing the foundation for future specialized graphs.
- **Negative**:
  - Requires careful graph design with termination guards to prevent infinite retrieval cycles.

---

## ADR-004: Tree-sitter AST Structural Chunking with Context Injection

### Status
Accepted

### Context
Splitting code files arbitrarily every fixed number of characters or tokens severs function definitions, splits class signatures, and loses enclosing context (e.g. class name or decorators), degrading embedding quality and retrieval precision.

### Decision
We will use **Tree-sitter** grammar parsers to parse source code into Abstract Syntax Trees (AST) and chunk along semantic boundaries (classes, functions, methods, interface definitions).
- **Initial Language Scope**: TypeScript, JavaScript, Python, Markdown, JSON, YAML.
- **Context Injection**: Prepend metadata headers to chunk text before embedding (e.g. `// File: src/auth/service.ts | Class: AuthService | Method: validateToken`).

### Consequences
- **Positive**:
  - Chunks preserve syntactic completeness and exact line boundaries for precision citation.
  - Dramatically improves semantic similarity matching.
- **Negative**:
  - Additional languages (Go, Rust, Java, C/C++) are deferred as future extensions.

---

## ADR-005: 3-Way Hybrid Search with Reciprocal Rank Fusion (RRF)

### Status
Accepted

### Context
Software engineering queries require both conceptual understanding (e.g. "how does session validation work?") and exact symbol matching (e.g. `validateOAuthToken_v2` or `src/api/auth.py`).

### Decision
We will implement a **3-Way Hybrid Search Pipeline**:
1. Dense Vector Similarity (`pgvector` HNSW Cosine).
2. Sparse Full-Text Search (PostgreSQL `ts_rank_cd` over `tsvector`).
3. Exact Path & Symbol Match Filtering.
Combined using **Reciprocal Rank Fusion (RRF)**:
$$RRF(d) = \sum_{m \in M} \frac{1}{60 + r_m(d)}$$

### Consequences
- **Positive**: High retrieval recall across both abstract concepts and exact function/class names.
- **Negative**: Requires generating and maintaining both `pgvector` HNSW indexes and PostgreSQL GIN full-text search indexes.

---

## ADR-006: ARQ as the Asynchronous Background Job Framework

### Status
Accepted

### Context
Repository ingestion, Tree-sitter parsing, batch embedding generation, and multi-hop repository analysis are CPU/IO-intensive tasks that must execute asynchronously without blocking HTTP requests.

### Decision
We will use **ARQ (Async Redis Queue)** as our background task framework, running on Python's native `asyncio` and Redis.
We establish three logical queues:
1. `ingestion`: Repository cloning, AST parsing, and chunking.
2. `embeddings`: Batch embedding generation with rate-limit retries.
3. `analysis`: Multi-step repository analysis and evaluation runs.

### Consequences
- **Positive**:
  - Native `async`/`await` support aligning seamlessly with FastAPI and async SQLAlchemy.
  - Extremely lightweight with minimal overhead compared to Celery.
  - Built-in job status tracking, timeouts, retries, and cron scheduling.
- **Negative**:
  - Requires Redis as the message broker.

---

## ADR-007: Incremental Repository Indexing via Content Hashing

### Status
Accepted

### Context
Re-indexing an entire repository on every commit is computationally expensive, slow, and wasteful for LLM embedding API quotas.

### Decision
We will implement an **Incremental Indexing Pipeline**:
1. Retrieve repository tree and compute SHA-256 content hashes for all files.
2. Compare hashes against previously indexed file records in PostgreSQL.
3. Process only modified or newly created files (parse, chunk, embed, upsert).
4. Prune stale chunks and embeddings for deleted files.
5. Full re-index remains available as an administrative recovery action.

### Consequences
- **Positive**: Near-instantaneous re-indexing on branch updates; minimal embedding API costs.
- **Negative**: Requires maintaining file-level content hashes and transactional chunk cleanup.

---

## ADR-008: EmbeddingProvider Abstraction & Multi-Version Vector Schema

### Status
Accepted

### Context
Hard-coding a single embedding model (e.g. OpenAI or Gemini) prevents future model upgrades or embedding provider switching without major database refactoring.

### Decision
1. Implement an `EmbeddingProvider` abstract interface supporting multiple providers (Google Gemini `text-embedding-004`, OpenAI `text-embedding-3-small`, etc.).
2. Store vector records in `chunk_embeddings` with explicit metadata: `chunk_id`, `provider`, `model`, `dimension`, `embedding_version`, `embedding`, and `created_at`.

### Consequences
- **Positive**: Allows seamless provider configuration and future vector model migrations without schema overhaul.
- **Negative**: Requires storing provider and model metadata per embedding record.

---

## ADR-009: Safe Agent Observability Without Exposing Private Reasoning

### Status
Accepted

### Context
Exposing raw model chain-of-thought or internal reasoning traces to the frontend can leak sensitive system instructions, create visual clutter, and degrade user trust with unrefined thoughts.

### Decision
We will emit structured **Safe Execution Events** over SSE (`understanding_query`, `searching_repository`, `retrieving_files`, `analyzing_evidence`, `validating_sources`, `generating_response`, `citations`). Internal model chain-of-thought traces will not be streamed to the client.

### Consequences
- **Positive**: Professional, predictable developer UI; protects internal prompts and raw model reasoning.
- **Negative**: Frontend must map discrete event types to UI status indicators.

---

## ADR-010: AES-256-GCM Credential Encryption & Untrusted Context Security

### Status
Accepted

### Context
GitHub access tokens and Personal Access Tokens must be stored securely at rest. Ingested repository content (code, comments, markdown) is untrusted and can contain prompt injection attacks.

### Decision
1. Encrypt all sensitive tokens at rest using **AES-256-GCM** authenticated encryption with keys loaded from environment variables.
2. Isolate all repository code inside `<repository_context>` XML tags in agent prompts with strict delimiter escaping and system instructions instructing the LLM never to execute repository content as instructions.

### Consequences
- **Positive**: Strong cryptographic security and robust defense against indirect prompt injection.
- **Negative**: Requires managing encryption keys and formatting prompts consistently.

---

## ADR-011: Frontend Technology Stack (Next.js 15, Tailwind, shadcn/ui, Monaco Editor)

### Status
Accepted

### Context
The user interface must deliver a modern, high-performance developer workspace with real-time streaming, code viewing, and source citations.

### Decision
We will use:
- **Next.js 15 App Router + React 19 + TypeScript**: Fast server-side rendering and streaming.
- **Tailwind CSS + shadcn/ui**: Modern, accessible, developer-focused component system.
- **Monaco Editor**: High-fidelity code viewing, diffing, and citation line-range highlighting.
- **TanStack Query**: Predictable server state caching.
*(React Flow for architecture visualization is planned for Phase 6).*

### Consequences
- **Positive**: Clean, fast, developer-grade UI.
- **Negative**: Monaco Editor requires dynamic imports to avoid SSR hydration issues.

---

## ADR-012: GitHub App Architecture for Granular, Read-Only Repository Authorization

### Status
Accepted

### Context
Forge AI requires access to user and organization repositories to discover repositories, inspect branches, and ingest codebase contents for semantic indexing. 

Traditional **OAuth Apps** use coarse scopes (e.g. `repo`). Under GitHub's authorization model, the OAuth `repo` scope grants blanket read **and write** access across all public and private repositories accessible to the user. There is no read-only scope in OAuth Apps for private repository code. Furthermore, OAuth Apps cannot be restricted by the user to specific repositories upon authorization.

In contrast, **GitHub Apps** provide fine-grained permissions, per-installation repository scoping, short-lived tokens, and organization-level security management.

### Decision
We will use a **GitHub App** as Forge AI's primary integration and authorization mechanism.

#### 1. Selected Permissions Model (Strict Least Privilege)
Forge AI will request only the following read-only permissions:
* **Repository Permissions**:
  * `Contents: Read` — Allows reading repository files, directories, branches, commits, trees, and downloading archive blobs for indexing. (Does NOT allow pushing commits, modifying files, creating branches, or deleting code).
  * `Metadata: Read` — Mandatory base permission required by GitHub to read basic repository metadata (repository name, owner, stars, visibility, default branch).
* **User / Account Permissions**:
  * `User Authorization (OAuth Web Flow)` — Identifies the authenticated GitHub user (`login`, `id`, `avatar_url`).

#### 2. Permissions Explicitly Excluded
The following permissions are strictly **NOT requested** in Phase 2 or Phase 3:
* $\times$ `Contents: Write` (No code writing or branch pushes).
* $\times$ `Pull Requests: Read/Write` (Deferred until Phase 6 PR Review workflows).
* $\times$ `Issues: Read/Write` (Not needed for repository ingestion).
* $\times$ `Workflows: Read/Write` (No CI/CD pipeline modification).
* $\times$ `Administration: Read/Write` (No repository settings modification).
* $\times$ `Webhooks: Read/Write` (Phase 2 uses on-demand API polling).

#### 3. Repository Scoping & Installation Model
During GitHub App installation, the user or organization administrator explicitly chooses whether to grant access to:
* **All repositories**, OR
* **Only select repositories** (e.g. granting Forge AI access to only `project-alpha`).

Forge AI can only discover and access repositories that were explicitly selected and granted by the user.

#### 4. Token Architecture & Lifecycle
* **Durable Metadata Persistence**:
  * We persist only durable installation and identity metadata in PostgreSQL: `github_user_id`, `github_username`, `github_installation_id`, `avatar_url`, and `created_at`/`updated_at`.
  * **Zero Database Persistence for Ephemeral Tokens**: Short-lived Installation Access Tokens (1 hour TTL) are **NOT** stored as durable records in PostgreSQL.
* **On-Demand Token Generation**:
  * The backend generates an authenticated RS256 JWT using the GitHub App's Private Key.
  * The backend calls GitHub's `POST /app/installations/{installation_id}/access_tokens` to obtain a fresh, short-lived Installation Access Token.
  * Tokens are used in-flight for API calls and discarded (or cached strictly in ephemeral memory with TTL < 50 minutes).
* **Granular Repository Scoping for Tokens**:
  * The token generation service accepts an optional `repository_ids: list[int] | None` parameter, allowing installation tokens to be scoped down to specific repository IDs on demand.
* **Storage & Encryption**:
  * Durable secrets (e.g., App Private Key, OAuth user refresh tokens) are encrypted at rest using **AES-256-GCM**.
  * Tokens and private keys never leave the server-side backend and are stripped from all API responses and logs.
* **Revocation**:
  * If a user uninstalls the GitHub App or removes repositories in their GitHub Settings, future token generation calls fail immediately. Disconnecting in Forge AI clears the local installation mapping.

### Consequences
- **Positive**:
  - True read-only access to private code without requesting dangerous write permissions.
  - Granular repository selection gives users full control over which repositories Forge AI can access.
  - Short-lived installation tokens (1 hour TTL) minimize blast radius if a session is compromised.
  - Organization-friendly: Supports GitHub Enterprise Cloud SAML SSO and organization approval policies.
  - Clean upgrade path: When Phase 6 introduces automated PR reviews, we can request `Pull Requests: Write` as an isolated, explicit permission upgrade.
- **Negative**:
  - Requires managing a GitHub App Private Key (`.pem`) for generating installation JWTs alongside Client ID / Client Secret.
