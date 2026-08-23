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
Accepted (Superseded in detail by ADR-013)

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
Accepted (Superseded in detail by ADR-014)

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
Accepted (Superseded in detail by ADR-015)

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
Accepted (Superseded in detail by ADR-016)

### Context
Hard-coding a single embedding model (e.g. OpenAI or Gemini) prevents future model upgrades or embedding provider switching without major database refactoring.

### Decision
1. Implement an `EmbeddingProvider` abstract interface supporting multiple providers (Google Gemini, OpenAI, etc.).
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
- **Negative**:
  - Requires managing a GitHub App Private Key (`.pem`) for generating installation JWTs alongside Client ID / Client Secret.

---

## ADR-013: Tree-sitter Structural AST Parsing & Context-Injected Semantic Chunking

### Status
Accepted

### Context
Line-based or character-count chunking cuts across function signatures, splits class bodies, and loses enclosing context (e.g. class name or decorators). For high-precision code retrieval, chunks must align with AST syntax nodes while retaining file and enclosing symbol context.

### Decision
1. Use **Tree-sitter** C-bindings in Python supporting: TypeScript, JavaScript, Python, Markdown, JSON, YAML.
2. Form chunks along AST node boundaries (`function_definition`, `class_declaration`, `method_definition`, `interface_declaration`, Markdown sections).
3. Prepend every chunk with a context header before embedding (`// File: ... | Class: ... | Method: ...`).
4. Apply an AST block-aware sliding window (600 tokens with 100 token overlap) only when individual AST nodes exceed 800 tokens.

### Consequences
- **Positive**: Syntactically complete chunks; accurate line-span citations; superior semantic search precision.
- **Negative**: Requires C-grammar dependencies in the Docker image.

---

## ADR-014: 3-Stage Hybrid Retrieval with Reciprocal Rank Fusion (RRF)

### Status
Accepted

### Context
Code queries range from conceptual ("how does session validation work?") to exact symbol lookups (`validateToken_v2`). Dense vector search alone misses exact identifiers, while keyword search misses abstract concepts.

### Decision
Implement a 3-Stage Hybrid Retrieval Pipeline combined via Reciprocal Rank Fusion (RRF):
1. **Dense Vector Search**: pgvector HNSW Cosine distance on 768d `gemini-embedding-2` vectors.
2. **Sparse Full-Text Search**: PostgreSQL `ts_rank_cd` on weighted GIN-indexed `tsvector`.
3. **Exact Symbol / Path Matching**: Boosted exact matches on symbol names and file paths.
$$RRF(d) = \sum_{m \in M} \frac{w_m}{60 + r_m(d)}$$
Initial weights ($w_{\text{dense}}=1.0, w_{\text{sparse}}=0.8, w_{\text{symbol}}=1.2$) will be calibrated against benchmark datasets.

### Consequences
- **Positive**: Comprehensive recall across both conceptual and exact symbol queries.
- **Negative**: Requires computing query embeddings and executing both vector and text searches.

---

## ADR-015: Ephemeral Streaming Tarball Ingestion & Atomic Index Version Promotion

### Status
Accepted

### Context
Buffering large repository archives into server RAM or holding long database transactions across slow external embedding API calls causes memory exhaustion and database lock starvation.

### Decision
1. **Streaming Ingestion**: Stream repository tarballs via GitHub API directly through an archive reader, unpacking only bounded per-file buffers in memory.
2. **Atomic Index Versioning**: Introduce `repository_index_versions` (`BUILDING` $\rightarrow$ `VALIDATED` $\rightarrow$ `ACTIVE`).
3. **Transaction Boundaries**: External embedding calls occur outside database transactions. Short DB transactions are used to persist draft chunks and execute atomic version promotion.
4. **ARQ Payloads**: Background jobs pass only lightweight IDs (`job_id`, `index_version_id`, `chunk_ids_batch`), never bulk chunk objects.

### Consequences
- **Positive**: Predictable low memory footprint; zero database lock contention; zero dangling failed indexes.
- **Negative**: Requires index version foreign key management.

---

## ADR-016: Unified 768d Vector Space with gemini-embedding-2 & EmbeddingProvider Abstraction

### Status
Accepted

### Context
We need high-quality code embeddings with reasonable cost and latency, while retaining multi-provider flexibility without introducing multi-dimensional schema complexity.

### Decision
1. Use **Google `gemini-embedding-2`** with a standardized **768 output dimension** as the primary vector space for Phase 3.
2. Retain the `EmbeddingProvider` abstract base class to support alternate providers (e.g. OpenAI `text-embedding-3-small`).
3. Store `provider`, `model`, `dimension`, and `embedding_version` metadata in `chunk_embeddings` for future vector migrations.
4. Use initial HNSW parameters: `m = 16`, `ef_construction = 64`.

### Consequences
- **Positive**: Fast, cost-effective vector search; clean single-dimension schema; future-proof provider switching.
- **Negative**: Changing default providers in the future requires re-indexing.

---

## ADR-017: Controlled Write Architecture & Strict Read/Write Tool Isolation

### Status
Accepted

### Context
Phase 4 provided read-only repository understanding (`search_repository`, `search_symbol`, `get_file`). Phase 5 introduces code modification capabilities. Mixing read and write permissions or granting agents unconstrained write access can cause unintended file corruption, loss of repository integrity, and security vulnerabilities.

### Decision
1. Strictly separate read tools from write tools at the architectural layer.
2. Read operations execute directly against the Phase 3 intelligence database (PostgreSQL + pgvector).
3. Write operations (`propose_patch`, `apply_patch`, `revert_patch`) operate strictly within an ephemeral `AgentWorkspace` and never touch persistent branch storage without explicit human sign-off.
4. Remote mutation tools (`push_branch`, `create_pull_request`) require a separate, cryptographically validated Human Approval token.

### Consequences
- **Positive**: Eliminates risk of accidental repository mutation; provides clear authorization boundaries; enforces least privilege per agent turn.
- **Negative**: Requires multi-phase orchestration and state persistence across approval boundaries.

---

## ADR-018: Ephemeral Sandbox Execution Model with gVisor / Docker Isolation

### Status
Accepted

### Context
Executing agent-generated code, compilation steps, linters, and unit tests directly on the Forge AI backend host creates severe security risks: arbitrary code execution, host file system traversal, socket sniffing, and credential theft (database credentials, API keys, `.env`).

### Decision
1. Execute all test, linter, and build commands inside ephemeral, disposable Docker containers with `gVisor` (`runsc`) isolation.
2. Apply strict resource limits per container: Max 2.0 vCPUs, 2048 MB RAM, 4 GB tmpfs storage, max 128 PIDs, and a 120-second execution timeout.
3. Completely sever network access (`--network=none`) during test execution to prevent data exfiltration and reverse shells.
4. Mount root filesystem as read-only; only `/workspace` is writable. Never mount `/var/run/docker.sock`, host `.env`, or backend database credentials into the container.

### Consequences
- **Positive**: Host system and tenant data are completely protected from malicious or buggy agent-generated code.
- **Negative**: Adds minor container creation/destruction latency per test execution cycle.

---

## ADR-019: Mandatory Human-in-the-Loop (HITL) Approval Boundary for State-Mutating Operations

### Status
Accepted

### Context
Autonomous LLM agents are non-deterministic and can produce unintended changes, hallucinated patches, or disruptive git commits. Enterprise software engineering demands human oversight before persistent repository modifications are enacted.

### Decision
1. Implement mandatory **Human Approval Gates** prior to executing persistent side effects:
   - **Gate 1 (Plan Approval)**: Human reviews and approves proposed file modification strategy.
   - **Gate 2 (Diff Approval)**: Human reviews visual diffs, line additions/deletions, and test execution reports.
   - **Gate 3 (Publish Approval)**: Human signs off before any remote branch is pushed or GitHub PR is created.
2. The agent graph pauses at `AWAITING_APPROVAL` and emits SSE events (`agent.approval_required`). Execution resumes only upon receiving an authenticated approval endpoint request.

### Consequences
- **Positive**: Guarantees human oversight; prevents accidental automated branch pollution; delivers full transparency for auditability.
- **Negative**: Workflow is asynchronous and requires user interaction to finalize pull requests.

---

## ADR-020: Isolated Agent Workspace & Worktree Lifecycle

### Status
Accepted

### Context
Multiple users or concurrent agent sessions working on the same repository must not mutate the same working directory or interfere with each other's in-progress changes.

### Decision
1. Model workspace state using `AgentWorkspace` database entities linked to unique Git worktrees (`/tmp/forge_workspaces/{workspace_id}`).
2. Each agent session provisions an independent worktree branched off the target commit SHA.
3. Workspaces follow a strict state machine (`CREATED` $\rightarrow$ `PREPARED` $\rightarrow$ `MODIFIED` $\rightarrow$ `TESTING` $\rightarrow$ `REVIEW` $\rightarrow$ `COMMITTED` $\rightarrow$ `DESTROYED`).
4. Support instant transactional rollbacks (`git checkout -- . && git clean -fd`).
5. Enforce an automated reaper for workspaces exceeding a 60-minute Time-To-Live (TTL).

### Consequences
- **Positive**: Full concurrency isolation; zero cross-session file contamination; instantaneous rollbacks.
- **Negative**: Requires disk space management and background worker cleanup routines.

---

## ADR-021: Structured Patch-Based Code Modification Model

### Status
Accepted

### Context
Prompting LLMs to output entire file contents for minor changes is slow, expensive in token consumption, prone to hallucination in unmodified sections, and makes diff review cumbersome.

### Decision
1. Enforce structured, hunk-based patch objects (`AgentPatch`) containing `file_path`, `operation` (`create`, `modify`, `delete`), `old_content_hash`, `new_content_hash`, `hunks`, and `explanation`.
2. Validate `old_content_hash` before applying to ensure the underlying file has not drifted.
3. Apply patches atomically using AST-aware hunk application with exact line-boundary matching.
4. Render structured hunks directly in Monaco Editor diff components for human review.

### Consequences
- **Positive**: Minimal token usage; atomic rollback capability; precise line-level attribution; prevents file drift bugs.
- **Negative**: Requires server-side patch parsing and fuzz-matching logic when minor whitespace differences occur.

---

## ADR-022: Centralized Multi-Agent Orchestration with Deterministic State Transitions

### Status
Accepted

### Context
Phase 5 used a single monolithic agent for retrieval, planning, patching, testing, and Git operations. Complex multi-step software engineering tasks require specialized cognitive roles (planning, coding, testing, review) without suffering from prompt confusion, sycophancy, or context exhaustion. Uncontrolled peer-to-peer swarms introduce non-deterministic execution and safety risks.

### Decision
1. Implement a **Centralized Multi-Agent Orchestration Architecture** governed by an authoritative LangGraph StateGraph supervisor (`EngineeringOrchestrator`).
2. Decompose engineering workflows into four specialized subagents:
   - **Planner Agent**: Read-only codebase investigation, symbol lookup, and `ImplementationPlan` synthesis.
   - **Coder Agent**: Context-grounded diff and patch synthesis within ephemeral workspaces.
   - **Tester Agent**: Automated test execution and failure analysis inside non-networked `gVisor` containers.
   - **Reviewer Agent**: Adversarial static security and regression analysis without mutation capabilities.
3. All inter-agent handoffs must route deterministically through the supervisor node.

### Consequences
- **Positive**: High determinism, inspectable state transitions, eliminates swarm deadlocks, isolates context windows per role.
- **Negative**: Adds graph routing nodes and requires typed message handoffs.

---

## ADR-023: Specialized Role Boundaries and Tool Access Segmentation

### Status
Accepted

### Context
Granting broad tool execution privileges (e.g. running tests, applying patches, proposing diffs) to all agents increases the attack surface for prompt injection and accidental repository mutation.

### Decision
1. Segment tool access strictly by agent role:
   - `Planner`: Read-only retrieval and symbol tools (`search_repository`, `search_symbol`, `get_file`).
   - `Coder`: Read-only tools + `propose_patch`.
   - `Tester`: `run_tests` (restricted to allowlisted commands in sandbox).
   - `Reviewer`: Read-only retrieval and AST inspection tools.
2. State-mutating operations (`apply_patch`, `git_commit`, `git_push`, `create_pull_request`) remain strictly inaccessible to autonomous agent execution and require explicit human approval.

### Consequences
- **Positive**: Prevents unauthorized lateral movement or bypass of safety gates even in the event of prompt injection.
- **Negative**: Agents must coordinate through structured handoffs rather than executing side-effects directly.

---

## ADR-024: Hybrid Shared-State Model (LangGraph Typed State + PostgreSQL Persistence)

### Status
Accepted

### Context
Multi-agent systems require sharing contextual artifacts (plans, patches, test outputs, review findings) between subagents while maintaining queryable auditability for human reviewers and persistent task history.

### Decision
1. Use a **Hybrid Shared-State Architecture**:
   - **Transient Loop State**: In-memory LangGraph `MultiAgentState` TypedDict for rapid subagent handoffs.
   - **Persistent Relational State**: PostgreSQL tables (`AgentTask`, `AgentApproval`, `AgentPatch`, `AgentTestExecution`, `AgentReview`, `AgentPullRequest`) for audit trails and UI streaming.
2. Sensitive credentials (API keys, GitHub tokens) are strictly excluded from state serialization.

### Consequences
- **Positive**: Immediate consistency during execution; permanent auditability; zero external message broker dependencies.
- **Negative**: Requires synchronization checkpoints between LangGraph node completion and database persistence.

---

## ADR-025: Preservation of 5-Gate Human-in-the-Loop Authority in Multi-Agent Execution

### Status
Accepted

### Context
Introducing multi-agent autonomy could tempt automated self-approval loops (e.g. Reviewer Agent approving Coder Agent's patch automatically). Enterprise safety invariants require that software mutations remain human-authorized.

### Decision
1. Preserve all **5 Human Approval Gates** established in Phase 5:
   - **Gate 1**: Plan Approval
   - **Gate 2**: Patch Diff Approval
   - **Gate 3**: Commit Approval
   - **Gate 4**: Remote Push Approval
   - **Gate 5**: Pull Request Creation Approval
2. The Reviewer Agent provides structured advisory feedback (`APPROVED` or `CHANGES_REQUESTED` with line-level findings) to assist the human reviewer, but possesses **zero authority** to execute persistent mutations.

### Consequences
- **Positive**: Guarantees absolute human oversight; prevents accidental repository pollution or autonomous privilege escalation.
- **Negative**: Human reviewer interaction is mandatory before changes are pushed to remote repositories.

---

## ADR-026: Hierarchical Iteration, Budget, and Timeout Guardrails

### Status
Accepted

### Context
Autonomous multi-agent feedback loops (e.g. Tester failure $\rightarrow$ Coder repair $\rightarrow$ Reviewer failure $\rightarrow$ Coder repair) can produce infinite cycles and runaway LLM token costs if unbounded.

### Decision
1. Enforce strict hierarchical execution guardrails:
   - `MAX_TOTAL_WORKFLOW_ITERATIONS`: 15
   - `MAX_PLANNER_INVESTIGATION_STEPS`: 5
   - `MAX_CODER_RETRY_CYCLES`: 3
   - `MAX_TEST_REPAIR_LOOPS`: 3
   - `MAX_REVIEW_ITERATIONS`: 2
   - `MAX_TOTAL_TOOL_INVOCATIONS`: 30
   - `MAX_WORKFLOW_EXECUTION_SECONDS`: 600 (10 minutes)
   - `MAX_TOKEN_BUDGET_PER_TASK`: 150,000 tokens
2. If any threshold is reached, the Orchestrator halts execution gracefully, releases ephemeral locks, and transitions the task to `WAITING_HUMAN_INTERVENTION`.

### Consequences
- **Positive**: Prevents infinite loops, bounds maximum per-task cost, and protects LLM provider rate limits.
- **Negative**: Complex multi-file tasks requiring $> 15$ iterations must be decomposed into smaller user objectives.


