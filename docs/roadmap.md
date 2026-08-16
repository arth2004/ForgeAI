# Forge AI — Implementation Roadmap

## Overview & Development Philosophy

Forge AI is constructed in discrete, testable phases. Each phase establishes a verified, runnable baseline before advancing. We avoid prototype throwaways by adhering to strict types, automated tests, and modular domain design from Day 1.

Phase 1 is intentionally focused on the **Foundational Platform** (monorepo, backend, frontend, database, Redis, ARQ worker, auth foundation, and Docker Compose) before any repository ingestion or AI features are built.

---

## Phase Matrix

| Phase | Focus Area | Deliverables | Verification Gate |
| :--- | :--- | :--- | :--- |
| **Phase 0** | **Architecture & Design** | `docs/architecture.md`, `docs/roadmap.md`, `docs/decisions.md` | Architectural review & stakeholder sign-off |
| **Phase 1** | **Foundational Platform** | Monorepo setup, Next.js 15, FastAPI, Postgres + pgvector, Redis, ARQ worker, Auth foundation, Healthchecks, Docker Compose | `docker compose up` starts all services; DB migrations pass; automated CI tests green |
| **Phase 2** | **GitHub Integration** | GitHub OAuth, Repo Discovery, Branch Switcher, Project Creation, Webhooks | User connects GitHub, views repo list, imports a repo, views file tree |
| **Phase 3** | **Repository Intelligence & Ingestion** | Tree-sitter AST parser (TS/JS/Py/MD/JSON/YAML), Semantic Chunking, EmbeddingProvider, pgvector, ARQ Ingestion Worker, Incremental Sync, Hybrid Retrieval | Ingest real repo in ARQ worker, verify chunks in DB, execute hybrid search query |
| **Phase 4** | **Project-Aware AI Assistant** | Streaming SSE chat endpoint, LangGraph Project Assistant, Safe Status Events, Citation Linker, Monaco Source Viewer | Multi-turn chat answers repo questions with clickable, verified citations |
| **Phase 5** | **Agent Platform (LangGraph Expansion)** | Multi-hop Dependency Traversal, Specialized Agents (Repo Analyst, Doc Generator), Agent Execution Telemetry | Run deep repo analysis agent, verify multi-hop reasoning, inspect tool execution steps |
| **Phase 6** | **Developer Workflows** | Automated PR Review workflow, Test Generator, React Flow Architecture Visualizer, API Endpoint Explorer | View interactive repo architecture graph, review PR diff with categorized findings |
| **Phase 7** | **Model Context Protocol (MCP)** | `forge-code-server`, `forge-git-server`, MCP Client wrapper, Sandboxed Tool Execution | Agent invokes MCP tools across repo sandbox with explicit permission checks |
| **Phase 8** | **AI Evaluation & Observability** | OpenTelemetry tracing, Token/Cost telemetry, Lightweight Evaluation Dataset Runner | Run automated evaluation suite measuring Precision@K, Recall@K, Groundedness |
| **Phase 9** | **Production Hardening & Polishing** | Rate limiting, Redis caching layer, Security audit, Comprehensive Docs, CI/CD pipeline | End-to-end smoke test passing in CI, zero lint/type errors, production Docker build verified |

---

## Detailed Phase Breakdown

### Phase 0 — Architecture & Design (Current)
- [x] Workspace inspection.
- [x] High-level architectural specification (`docs/architecture.md`).
- [x] Architecture Decision Records (`docs/decisions.md`).
- [x] Granular roadmap (`docs/roadmap.md`).
- [ ] User review and approval.

---

### Phase 1 — Foundational Platform (Strict Foundation Scope)
* **Backend**:
  - FastAPI async project structure with `app/api`, `app/core`, `app/models`, `app/schemas`, `app/services`.
  - SQLAlchemy 2.0 async engine + Alembic migration configuration.
  - Redis connection pool for caching & job broker.
  - Base models: `User`, `Organization`, `Membership`, `Project`, `Repository`, `RepositoryBranch`.
  - JWT auth & AES-256-GCM encrypted secret storage for tokens.
  - Comprehensive health check (`/api/v1/health`) checking DB, Redis, and ARQ worker readiness.
* **Worker**:
  - ARQ worker entrypoint and worker pool configuration with logical queues (`ingestion`, `embeddings`, `analysis`).
  - Sample background ping/health task.
* **Frontend**:
  - Next.js 15 App Router with TypeScript and Tailwind CSS.
  - shadcn/ui component integration (Button, Dialog, Dropdown, Table, Toast, Tooltip, Tabs).
  - TanStack Query setup with unified API client.
  - Layout shell with responsive sidebar, navigation, theme toggle (Dark/Light), and user avatar.
* **Infrastructure & Testing**:
  - `docker-compose.yml` orchestrating `postgres` (with pgvector), `redis`, `api`, and `worker`.
  - Pytest setup with `pytest-asyncio` and test database fixtures.
  - Vitest / React Testing Library setup for frontend.

> [!NOTE]
> Phase 1 deliberately does NOT include repository indexing, Tree-sitter, embedding generation, LangGraph agents, MCP, PR review, or evaluation dashboards.

---

### Phase 2 — GitHub Integration
* **Backend**:
  - GitHub OAuth flow with state verification.
  - Encrypted GitHub token storage via AES-256-GCM.
  - GitHub API Client: Fetch user repositories (public & private), branches, commit history, and tree structure.
  - Repository linking to Projects with branch selection.
* **Frontend**:
  - GitHub connect button & OAuth callback handler.
  - Project creation wizard: select org, choose GitHub repo, pick branch.
  - Repository dashboard: repository cards, sync status, branch dropdown, file explorer tree.

---

### Phase 3 — Repository Intelligence & Ingestion
* **Ingestion Engine**:
  - File filtering engine (`.gitignore`, binaries, size limits, lockfiles, generated assets).
  - Tree-sitter AST parser supporting TypeScript, JavaScript, Python, Markdown, JSON, YAML.
  - Symbol & Scope extraction (functions, classes, interfaces, methods).
  - Chunking strategy: AST node-bounded chunks with context header injection (`// File: ... | Class: ... | Method: ...`).
* **Embedding & Storage**:
  - `EmbeddingProvider` abstraction supporting Google Gemini and OpenAI embeddings.
  - `chunk_embeddings` multi-version schema with HNSW index for cosine distance.
  - Full-text search `tsvector` generation and GIN index.
  - `code_dependencies` table schema for future dependency traversal.
* **Worker & Incremental Sync**:
  - ARQ async ingestion workers (`ingestion` and `embeddings` queues).
  - Incremental sync engine: SHA-256 hash comparison against existing database records.
  - Hybrid Search Engine combining dense vector similarity + sparse tsvector ranking via Reciprocal Rank Fusion (RRF).

---

### Phase 4 — Project-Aware AI Assistant
* **Backend**:
  - Unified `LLMGateway` supporting Google Gemini, OpenAI, and Anthropic.
  - LangGraph **Project Assistant** graph:
    `Query Understanding -> Retrieval -> Evidence Analysis -> Verification -> Response Synthesis + Citations`.
  - Safe status event dispatcher emitting sanitized status events over SSE without exposing raw chain-of-thought.
  - Multi-turn conversation persistence (`conversations`, `messages`, `citations`).
* **Frontend**:
  - Modern AI Chat UI with streaming markdown, code syntax highlighting, copy-to-clipboard.
  - Safe execution status indicator (e.g. "Searching repository...", "Analyzing code context...").
  - Interactive Citation Pills: clicking opens side drawer with Monaco Editor showing highlighted line ranges.
  - Token and latency metadata display per message.

---

### Phase 5 — Agent Platform (LangGraph Expansion)
* **LangGraph Multi-Agent Workflows**:
  - Multi-hop dependency traversal (following imports and callers).
  - **Repository Analyst Agent**: Deep architectural exploration across multiple files.
  - **Documentation Agent**: Automated module and API documentation synthesizer.
  - Safe agent execution telemetry.

---

### Phase 6 — Developer Workflows
* **Workflows**:
  - **PR Code Reviewer**: Diff parser, security & performance vulnerability auditor, structured finding cards (Severity, Category, Line, Fix).
  - **Architecture Explorer**: Interactive React Flow diagram generated from codebase analysis with clickable nodes mapping to files.
  - **API Explorer**: Automatic endpoint detection with schema viewer.
  - **Test Generator**: Unit test synthesizer with mock recommendations.

---

### Phase 7 — Model Context Protocol (MCP)
* **MCP Integration**:
  - Integration of standard Model Context Protocol.
  - `forge-code-server` for granular AST queries and safe file slicing.
  - `forge-git-server` for git blame, diff, and commit queries.
  - Dynamic agent tool binding via MCP client.

---

### Phase 8 — Evaluation & Observability
* **Observability**:
  - OpenTelemetry distributed tracing across HTTP requests, LangGraph nodes, and DB queries.
  - Token consumption and dollar-cost telemetry dashboard per project.
* **Lightweight Evaluation Suite**:
  - Curated evaluation dataset for codebase Q&A.
  - Automated evaluation harness computing Precision@K, Recall@K, Citation Accuracy, and Answer Groundedness.

---

### Phase 9 — Production Hardening
* **Security & Operations**:
  - Prompt injection defense testing & repository sanitization.
  - Sliding-window rate limiting per IP / User.
  - Redis query caching.
  - GitHub Actions CI/CD workflows for automated test runs, linting, and Docker container builds.
  - Comprehensive documentation suite (`docs/`).
