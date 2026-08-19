# Forge AI — Phase 4 Final Architecture

## 1. Executive Architecture Overview

Forge AI is an enterprise-grade AI software engineering platform. Phase 4 establishes a fully integrated, repository-grounded conversational AI agent. The architecture connects a modern Next.js frontend to an asynchronous FastAPI backend via Server-Sent Events (SSE), executing a LangGraph-driven reasoning and tool-use loop backed by the Phase 3 Repository Intelligence Engine (PostgreSQL, pgvector, Tree-sitter AST parsers, and hybrid RRF retrieval).

```
┌────────────────────────────────────────────────────────────────────────┐
│                                FRONTEND                                │
│                                                                        │
│  ProjectWorkspacePage (app/(dashboard)/projects/[id])                  │
│    ├── AgentChat Container                                             │
│    ├── AgentMessageList & AgentMessage                                 │
│    ├── AgentActivity (Progressive Tool Status)                         │
│    ├── AgentSources (Grounded Evidence Citations)                      │
│    ├── AgentComposer (Input & Stream Cancellation)                     │
│    └── useAgentChat Hook & parseSSEStream Client                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    │ POST /api/v1/agent/chat/stream
                                    │ Authorization: Bearer <JWT>
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                               API LAYER                                │
│                                                                        │
│  FastAPI Agent Router (/api/v1/agent)                                  │
│    ├── JWT Authentication & User Extraction                            │
│    ├── Tenant & Project/Repository/Branch Authorization                │
│    ├── AgentSession Context Binding & Reuse (models.AgentSession)      │
│    └── Streaming SSE & Non-Streaming REST Endpoints                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                             AGENT SERVICE                              │
│                                                                        │
│  AgentService (app/services/agent_service.py)                          │
│    ├── resolve_and_authorize_context()                                 │
│    ├── Session Lifecycle & Context Validation                          │
│    ├── LangGraph Execution Orchestration                              │
│    └── Structured SSE Event Dispatch (session.created, agent.*)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         LANGGRAPH REASONING LOOP                       │
│                                                                        │
│  StateGraph (app/agent/graph.py)                                       │
│    ├── START ──> agent_node (SystemMessage + Evidence Context)         │
│    │                  │                                                │
│    │                  ▼                                                │
│    │            tool_router                                            │
│    │            ├── [has tool calls & iterations < max]                │
│    │            │         ▼                                            │
│    │            │    tools_node (ToolRegistry + ToolUsageGuard)        │
│    │            │         │                                            │
│    │            │         └──> (loop back to agent_node)               │
│    │            └── [no tool calls OR iteration limit]                 │
│    │                      ▼                                            │
│    │                     END                                           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               ▼                    ▼                    ▼
┌────────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│ search_repository Tool │ │ search_symbol    │ │ get_file Tool        │
│ (Hybrid Dense+Sparse)  │ │ (AST Symbol DB)  │ │ (Bounded Slicing)    │
└──────────────┬─────────┘ └────────┬─────────┘ └──────────┬───────────┘
               │                    │                      │
               └────────────────────┼──────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    PHASE 3 REPOSITORY INTELLIGENCE                     │
│                                                                        │
│  HybridSearchEngine (Dense Cosine + Sparse tsvector + Symbol Boost)    │
│  Reciprocal Rank Fusion (RRF, k=60)                                    │
│  Tree-sitter AST Chunker (Python, TS, JS, Markdown, JSON, YAML)        │
│  Embedding Providers (Gemini gemini-embedding-2 / OpenAI / Mock)       │
│  PostgreSQL 16 + pgvector (HNSW Index) + SQLAlchemy Async Engine       │
│  Atomic Index Version Lifecycle (PENDING -> INDEXING -> ACTIVE)        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Responsibilities & Boundaries

### 2.1 Frontend Layer (`frontend/src/`)
- **`AgentChat`**: Top-level container mounted inside `ProjectWorkspacePage` tabs. Manages layout, context headers, error banners, and reset operations.
- **`useAgentChat`**: Custom React hook managing conversation state, `sessionId`, message history, progressive streaming updates, and `AbortController` cancellation.
- **`AgentMessageList` & `AgentMessage`**: Renders user queries and assistant responses with markdown text, collapsible tool execution progress, and citation grids.
- **`AgentActivity`**: Compact progress indicator showing active and completed tool actions (`search_repository`, `search_symbol`, `get_file`) without exposing hidden chain-of-thought.
- **`AgentSources`**: Deduplicated source cards displaying repository relative paths, line numbers, AST symbol badges, and copy helpers.
- **`AgentComposer`**: Accessible input box supporting Enter to send, Shift+Enter for newlines, max length enforcement (4,000 characters), and active stream termination.
- **`parseSSEStream`**: Streaming parser with full chunk-boundary resilience, handling split chunks, multi-event buffers, and graceful error recovery.

### 2.2 API Layer (`backend/app/api/v1/agent.py`)
- **`POST /api/v1/agent/chat`**: Synchronous request-response endpoint returning structured `AgentChatResponse`.
- **`POST /api/v1/agent/chat/stream`**: Direct `text/event-stream` SSE endpoint emitting lifecycle events:
  - `session.created`
  - `agent.started`
  - `agent.tool_call`
  - `agent.tool_result`
  - `agent.completed`
  - `agent.error`
- **Security & Authorization**: Validates JWT authentication and enforces that the requesting user owns or has access to the specified project, repository, and branch.

### 2.3 Agent Service Layer (`backend/app/services/agent_service.py`)
- **`resolve_and_authorize_context`**: Verifies project/repository/branch ownership, loads or creates database-backed `AgentSession` models, and rejects context conflicts (HTTP 409).
- **`execute_chat` & `stream_chat`**: Invokes the LangGraph agent graph, streams real-time execution steps, gathers structured citations, and enforces request timeout boundaries.

### 2.4 Agent Core & Reasoning Engine (`backend/app/agent/`)
- **`StateGraph` (`graph.py`)**: Asynchronous cyclic state graph with iteration protection (`MAX_AGENT_ITERATIONS = 5`).
- **`AgentConfig` (`config.py`)**: Immutable configuration binding LLM provider (`gemini`, `openai`, `mock`), temperature, model names, and iteration limits.
- **`DEFAULT_AGENT_SYSTEM_PROMPT` (`prompts.py`)**: Core system prompt enforcing grounding contract, tool selection criteria, evidence synthesis, and no-hallucination guarantees.
- **`ToolRegistry` & `ToolUsageGuard` (`tools/`)**: Tool validation, execution isolation, per-turn call limits, and automatic payload truncation.

### 2.5 Phase 3 Repository Intelligence Engine (`backend/app/services/`)
- **`HybridSearchEngine`**: Multi-modal code retrieval combining pgvector dense cosine search, PostgreSQL `tsvector` full-text search, and exact AST symbol matching via Reciprocal Rank Fusion (RRF, $k=60$).
- **`TreeSitterChunker`**: AST-aware semantic code chunker extracting classes, methods, functions, and interfaces across TS, JS, Python, Markdown, JSON, and YAML.
- **`EmbeddingService`**: Batch vector generation supporting Gemini `text-embedding-004` (768d), OpenAI `text-embedding-3-small`, and deterministic mock embeddings.

---

## 3. Data Flow & Lifecycle Walkthrough

### 3.1 New Conversation Turn
```
1. User enters query in AgentComposer
2. useAgentChat emits POST /api/v1/agent/chat/stream (session_id: null)
3. FastAPI validates JWT -> AgentService.resolve_and_authorize_context()
4. AgentService creates database AgentSession(user_id, project_id, repo_id, branch_id)
5. Stream emits event: session.created { "session_id": "..." }
6. AgentService builds LangGraph StateGraph with SystemMessage + UserMessage
7. agent_node runs LLM -> LLM returns tool_calls -> emits event: agent.tool_call
8. tool_router routes to tools_node -> executes repository tool -> emits event: agent.tool_result
9. LangGraph loops back to agent_node with ToolMessage evidence
10. LLM generates final grounded answer -> emits event: agent.completed
11. Frontend updates assistant card, renders answer & grounded source citations
```

### 3.2 Multi-Turn Follow-Up
```
1. User enters follow-up question
2. useAgentChat emits POST /api/v1/agent/chat/stream (session_id: "sess-1234")
3. AgentService verifies session ownership and checks project/repo/branch match
4. Stream reuses existing session without creating a new database record
5. LangGraph executes reasoning turn and returns grounded follow-up response
```

---

## 4. Security Architecture

1. **Tenant & Project Isolation**: All repository queries, AST symbol searches, and file slicing operations are strictly scoped by `repository_id` and authorized against the authenticated user's organization.
2. **Session Hijacking Protection**: `AgentSession` records verify `session.user_id == current_user.id`. Any unauthorized access is rejected with HTTP 403 Forbidden.
3. **Session Context Integrity**: Sessions are permanently bound to their initial project/repository context. Attempts to access another repository using an existing session are rejected with HTTP 409 Conflict.
4. **Path Traversal Guard**: `validate_safe_file_path()` ensures all file access requests reject absolute paths, null bytes, backslashes, and `..` directory traversal sequences.
5. **No Secret / Chain-of-Thought Leakage**:
   - Internal model planning text, raw tool JSON-RPC payloads, and prompt engineering internals are excluded from public API responses.
   - `sanitize_error()` strips API keys and credentials from logs and error messages.
   - UI renders only sanitized tool activity badges and user-facing answers.

---

## 5. Error & Failure Recovery Matrix

| Scenario | HTTP / Event Code | Backend Behavior | Frontend Presentation |
| :--- | :--- | :--- | :--- |
| **Unauthenticated Request** | `401 Unauthorized` | Rejects request before agent invocation | *"Your session has expired. Please sign in again."* |
| **Unauthorized Project Access** | `403 Forbidden` | Access control check fails | *"You do not have permission to access this project or repository."* |
| **Non-Existent Resource** | `404 Not Found` | Project or repository ID not found | *"The requested project, repository, or branch was not found."* |
| **Session Context Mismatch** | `409 Conflict` | Rejects mismatched repository/branch | *"This conversation is bound to a different repository context."* |
| **Malformed Payload** | `422 Unprocessable` | Pydantic validation rejects payload | *"Invalid message payload. Please verify your query length."* |
| **Rate Limit / Quota Exceeded** | `429 Too Many Requests` | Fast failure on LLM/Embedding 429 | *"Forge AI is temporarily rate-limited. Please try again shortly."* |
| **Agent Execution Timeout** | `504 Gateway Timeout` | Cancels graph execution after timeout | *"The agent took too long to respond. Try asking a more specific question."* |
| **Tool Execution Error** | `agent.tool_result (status=failed)` | Returns error string in `ToolMessage` to agent | Shows failed tool badge; agent attempts alternate tool or explains limitation |
| **Unindexed Repository** | `agent.error` | Tool guards reject unindexed repos | Informs user that repository indexing must be completed first |
| **Client Stream Cancellation** | `AbortError` | Terminates HTTP connection and reader lock | Preserves current conversation state and enables new queries |

---

## 6. Technical Debt & Future Considerations

- **P1**: Model provider streaming token granularity (current implementation emits turn-level SSE chunks; token-level streaming can be added when real-time streaming LLM providers are enabled).
- **P2**: Cross-session persistent chat history (Phase 4 focuses on active session binding; long-term message persistence across browser reloads is scheduled for future roadmap phases).
- **P2**: Incremental physical row-copying optimization during reindexing.
