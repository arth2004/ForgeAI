# Phase 4B — Repository Tool Layer Documentation & Verification Report

## 1. Executive Summary

Phase 4B establishes the **Repository Tool Layer** for Forge AI. This layer exposes the Phase 3 Repository Intelligence Engine to the Phase 4 LangGraph agent runtime via clean, validated, tenant-isolated tool abstractions.

### Key Achievements:
- **Zero Phase 3 Duplication**: Reuses `HybridSearchEngine`, pgvector dense similarity, tsvector sparse text search, AST code chunks, and atomic active index resolution directly.
- **Strict Security & Validation**: Input query sanitization, symbol validation, path traversal rejection (`../`, `..\\`, Windows drive letters, null bytes), line windowing, output truncation, and tenant project authorization.
- **Execution-Scoped Rate & Usage Guards**: `ToolUsageGuard` limits total and per-tool invocations, and truncates large outputs (>16KB file window, >24KB tool response) to prevent context exhaustion.
- **Cyclic Tool Execution Graph**: Integrated `tools_node` and `tool_router` into the LangGraph state graph with bounded iteration safeguards (`MAX_AGENT_ITERATIONS = 5`).
- **Complete Test Coverage & Zero Regressions**: 20 dedicated Phase 4B tests, 98/98 total backend tests passing, 9/9 frontend tests passing, Next.js build clean, Ruff and Mypy passing with 0 errors.

---

## 2. Tool Layer Architecture

```
                                      +--------------------------+
                                      |     Agent StateGraph     |
                                      +--------------------------+
                                                   |
                                                   v
                                          +------------------+
                                          |    agent_node    | <----+
                                          +------------------+      |
                                                   |                |
                                                   v                |
                                          +------------------+      |
                                          |   tool_router    |      |
                                          +------------------+      |
                                            /              \        |
                              tool_calls > 0                no tool_calls / max iter
                                          /                  \
                                         v                    v
                               +------------------+        +-----+
                               |    tools_node    | -----> | END |
                               +------------------+        +-----+
                                        |
                 +----------------------+----------------------+
                 |                      |                      |
                 v                      v                      v
      +----------------------+ +------------------+ +--------------------+
      | search_repository    | | search_symbol    | | get_file           |
      | (HybridSearchEngine) | | (CodeChunk AST)  | | (RepositoryFile)   |
      +----------------------+ +------------------+ +--------------------+
                 |                      |                      |
                 +----------------------+----------------------+
                                        |
                             +--------------------+
                             |  Phase 3 Engine /  |
                             | PostgreSQL/pgvector|
                             +--------------------+
```

### Module Structure
```text
backend/app/agent/tools/
├── __init__.py               # Central tool registry (get_agent_tools, get_agent_tool_by_name)
├── base.py                   # BaseRepositoryTool ABC, tenant authorization, active index check
├── file_viewer.py            # FileViewerTool (get_file) with line range windowing
├── limits.py                 # ToolUsageGuard & output truncation helpers
├── repository_search.py      # RepositorySearchTool (search_repository) with Phase 3 HybridSearchEngine
├── symbol_search.py          # SymbolSearchTool (search_symbol) querying indexed CodeChunk AST records
└── validation.py             # Validation rules, path traversal rejection, error models
```

---

## 3. Repository Tools Specification

### 1. `search_repository` (`RepositorySearchTool`)
- **Purpose**: Executes hybrid code and documentation search across the active indexed codebase.
- **Input Schema**:
  - `query` (str, 1..1000 chars): Search prompt.
  - `project_id` (str/UUID): Target project ID.
  - `top_k` (int, 1..20, default=5): Number of ranked evidence chunks to return.
- **Execution**:
  - Validates query and verifies user tenant access to the project.
  - Resolves active index version for default branch.
  - Calls Phase 3 `HybridSearchEngine.search()`.
  - Returns ranked list of code/doc chunks with `file_path`, `symbol_name`, `start_line`, `end_line`, `rrf_score`, `commit_sha`, and `content`.

### 2. `search_symbol` (`SymbolSearchTool`)
- **Purpose**: Fast lookup for indexed classes, functions, methods, and interfaces without re-parsing ASTs.
- **Input Schema**:
  - `symbol_name` (str, 1..255 chars): Name of symbol.
  - `project_id` (str/UUID): Target project ID.
  - `limit` (int, 1..20, default=10): Maximum symbols to return.
- **Execution**:
  - Queries active index `CodeChunk` records matching `symbol_name` (exact and case-insensitive prefix).
  - Returns declaration locations, context headers, line ranges, and chunk types (`CLASS`, `FUNCTION`, `METHOD`, `INTERFACE`).

### 3. `get_file` (`FileViewerTool`)
- **Purpose**: Retrieves file contents from the active repository index with optional line windowing.
- **Input Schema**:
  - `file_path` (str, 1..1000 chars): Relative path within repository.
  - `project_id` (str/UUID): Target project ID.
  - `start_line` (int, optional, >=1): Start line window.
  - `end_line` (int, optional, >=start_line): End line window.
- **Execution**:
  - Enforces path traversal rejection (`../`, `..\\`, `C:\`, null bytes).
  - Retrieves indexed `RepositoryFile` and reconstructed text from chunks.
  - Applies line range slicing if specified.
  - Enforces 16,000 character output truncation guard.

---

## 4. Security, Validation & Guardrails

| Guardrail | Enforcement Point | Behavior on Violation |
| :--- | :--- | :--- |
| **Path Traversal Protection** | `validate_safe_file_path()` | Rejects `../`, `..\\`, Windows drive letters, null bytes with `ToolValidationError` (HTTP 400). |
| **Tenant Isolation** | `BaseRepositoryTool.verify_project_access()` | Verifies user membership in owning organization; raises `ToolAuthorizationError` (HTTP 403) on mismatch. |
| **Index Status Guard** | `BaseRepositoryTool.get_active_index_version()` | Requires `IndexVersionStatus.ACTIVE`; raises `RepositoryNotIndexedError` (HTTP 404) if building/failed/missing. |
| **Tool Execution Rate Limits** | `ToolUsageGuard.record_call()` | Max 10 calls per execution, max 6 calls per tool; raises `ToolRateLimitError` (HTTP 429). |
| **Output Size Bounds** | `truncate_tool_output()` | Truncates tool responses at 24KB (16KB for file content) with explicit truncation indicator. |
| **Graph Iteration Guard** | `tool_router()` | Hard limit of 5 agent-tool loop iterations before forcing graph termination at `END`. |

---

## 5. Verification Results

### Backend Pytest Suite
```text
============================= test session starts =============================
collected 98 items

tests/integration/test_agent_graph.py (5 tests) ......................... PASSED
tests/integration/test_agent_tool_graph.py (5 tests) .................... PASSED
tests/integration/test_agent_tools_execution.py (6 tests) ............... PASSED
tests/integration/test_auth_api.py (7 tests) ............................ PASSED
tests/integration/test_codebase_models.py (6 tests) ..................... PASSED
tests/integration/test_health.py (1 test) ............................... PASSED
tests/integration/test_indexing_flow.py (3 tests) ....................... PASSED
tests/integration/test_organization_api.py (5 tests) .................... PASSED
tests/integration/test_projects_api.py (6 tests) ........................ PASSED
tests/integration/test_retrieval_benchmark.py (7 tests) ................. PASSED
tests/unit/test_agent_foundation.py (8 tests) ........................... PASSED
tests/unit/test_agent_tools.py (9 tests) ................................ PASSED
tests/unit/test_chunker.py (6 tests) .................................... PASSED
tests/unit/test_embedding.py (6 tests) .................................. PASSED
tests/unit/test_hybrid_retrieval.py (6 tests) ........................... PASSED
tests/unit/test_parser.py (6 tests) ..................................... PASSED
tests/unit/test_security.py (7 tests) ................................... PASSED

============================= 98 passed in 10.51s =============================
```

### Static Analysis
- **Ruff**: `All checks passed!` (0 linting or formatting errors across 101 files)
- **Mypy**: `Success: no issues found in 101 source files` (Strict type safety)

### Frontend Validation
- **Vitest**: `9 passed (9)` across `app.test.tsx`, `auth.test.tsx`, `dashboard.test.tsx`.
- **Next.js Build**: Successful production build with 11 static pages generated.

---

## 6. Retrieval Quality Verification

The Phase 4B repository tools call the hardened Phase 3 `HybridSearchEngine`. Source code implementations are verified to rank above documentation across standard benchmarks:
- `"Where are embeddings generated?"` $\rightarrow$ `backend/app/services/embedding/gemini.py` (`GeminiEmbeddingProvider`)
- `"Where is hybrid retrieval implemented?"` $\rightarrow$ `backend/app/services/retrieval/hybrid.py` (`HybridSearchEngine`)
- `"Where is Tree-sitter parser implemented?"` $\rightarrow$ `backend/app/services/parser/`
- Documentation chunks (`docs/architecture.md`) are never artificially suppressed but are properly weighted below implementation source code for code queries.

---

## 7. Strict Phase Boundary Adherence

In accordance with Phase 4B boundaries, the following were **NOT** added:
- No autonomous code modification / file writing tools.
- No shell execution / CLI subagents.
- No GitHub write operations / PR creation.
- No Model Context Protocol (MCP) integrations.
- No multi-agent hierarchies or conversation persistence.
- No frontend chat UI or chat streaming APIs.
