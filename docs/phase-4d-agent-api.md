# Phase 4D — Public Agent Chat API

## 1. Architecture

Phase 4D exposes the internal Phase 4 LangGraph reasoning engine through a secure, public FastAPI interface supporting both non-streaming JSON responses and real-time Server-Sent Events (SSE) streaming.

```
                    +--------------------------------+
                    |          HTTP Client           |
                    +--------------------------------+
                                   |
                  POST /api/v1/agent/chat (or /chat/stream)
                                   |
                                   v
                    +--------------------------------+
                    |    FastAPI Agent Router        |
                    |    (app/api/v1/agent.py)       |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |  Authentication & Membership   |
                    |  (JWT + Org Project Access)    |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |    Session Context Binding     |
                    |  (AgentSession Validation/DB)  |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |        AgentService            |
                    |  (app/services/agent_service)  |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |      LangGraph StateGraph      |
                    |    (app/agent/graph.py)        |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |    Repository Tool Layer       |
                    |    (search_repo, symbol, file) |
                    +--------------------------------+
                                   |
                                   v
                    +--------------------------------+
                    |   Phase 3 Retrieval Services   |
                    |    (Hybrid, AST, DB Chunks)    |
                    +--------------------------------+
```

---

## 2. Endpoints

### 1. Execute Agent Chat Turn
- **Method / Path**: `POST /api/v1/agent/chat`
- **Authentication**: `Authorization: Bearer <JWT>`
- **Content-Type**: `application/json`
- **Response**: `application/json` (when `stream=false`) or `text/event-stream` (when `stream=true`)

### 2. Stream Agent Chat Turn (SSE Direct)
- **Method / Path**: `POST /api/v1/agent/chat/stream`
- **Authentication**: `Authorization: Bearer <JWT>`
- **Content-Type**: `application/json`
- **Response**: `text/event-stream`

---

## 3. Schemas

### Request Schema (`AgentChatRequest`)
```json
{
  "message": "Where is JWT authentication implemented?",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "repository_id": "8fa85f64-5717-4562-b3fc-2c963f66afa6",
  "branch_id": "9fa85f64-5717-4562-b3fc-2c963f66afa6",
  "session_id": "1fa85f64-5717-4562-b3fc-2c963f66afa6",
  "stream": false
}
```

### Non-Streaming Response Schema (`AgentChatResponse`)
```json
{
  "session_id": "1fa85f64-5717-4562-b3fc-2c963f66afa6",
  "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "repository_id": "8fa85f64-5717-4562-b3fc-2c963f66afa6",
  "branch_id": "9fa85f64-5717-4562-b3fc-2c963f66afa6",
  "answer": "JWT authentication is implemented in `backend/app/core/security.py` using `create_access_token` and `decode_access_token`.",
  "sources": [
    {
      "file_path": "backend/app/core/security.py",
      "symbol_name": "create_access_token",
      "start_line": 20,
      "end_line": 35,
      "commit_sha": "c0ffee1234567890abcdef1234567890abcdef12"
    }
  ],
  "metadata": {
    "iterations": 2,
    "tool_calls": 1,
    "duration_ms": 234.5,
    "retrieved_sources_count": 3
  }
}
```

---

## 4. SSE Stream Events

When streaming (`stream=true` or `/chat/stream`), the API emits real-time Server-Sent Events conforming to the `text/event-stream` format:

| Event Type | Description | Payload Data |
| :--- | :--- | :--- |
| **`session.created`** | Emitted when session context is resolved/bound. | `{"session_id": "...", "project_id": "...", "repository_id": "...", "branch_id": "..."}` |
| **`agent.started`** | Emitted when reasoning loop starts turn. | `{"session_id": "...", "iteration": 1}` |
| **`agent.tool_call`** | Emitted when the agent requests a tool. | `{"tool": "search_repository", "call_id": "...", "iteration": 1, "args": {...}}` |
| **`agent.tool_result`** | Emitted when a tool finishes execution. | `{"tool": "search_repository", "status": "success", "duration_ms": 12.3}` |
| **`agent.completed`** | Emitted upon final response generation. | `{"session_id": "...", "answer": "...", "sources": [...], "metadata": {...}}` |
| **`agent.error`** | Emitted on unrecoverable execution errors. | `{"error": "...", "status_code": 403}` |

---

## 5. Security & Isolation

1. **Authentication**: Mandatory JWT Bearer token via `get_current_user`. Missing/invalid tokens return `401 Unauthorized`.
2. **Tenant & Project Isolation**: Verifies caller is a member of the project's organization (`Membership`). Unauthorized projects return `403 Forbidden`.
3. **Repository & Branch Boundary**: Verifies repository belongs to the specified project and branch belongs to the repository. Foreign repository IDs return `409 Conflict`.
4. **Session Context Binding**:
   - `AgentSession` records `user_id`, `project_id`, `repository_id`, and `branch_id`.
   - Reusing a session owned by another user returns `403 Forbidden`.
   - Attempting to switch project or repository on an existing session returns `409 Conflict`.
5. **Sanitization & Hygiene**: Secret tokens, API keys, hidden system prompts, raw LLM payloads, and internal chain-of-thought tokens are never exposed.

---

## 6. Session Lifecycle & Scope Boundaries

A session in Phase 4D represents an **operational context binding** (User $\leftrightarrow$ Project $\leftrightarrow$ Repository $\leftrightarrow$ Branch).

> [!NOTE]
> Persistent conversation message history, conversation summarization, semantic memory, and cross-session user preferences belong to future phases and are intentionally NOT part of Phase 4D.

---

## 7. Non-Goals

Phase 4D strictly does NOT implement:
- Frontend Chat UI (React components, Next.js chat pages).
- Long-term database message history or memory stores.
- Autonomous repository mutation, file editing, or shell execution.
- GitHub pull requests or issue comments.
- Model Context Protocol (MCP) servers or multi-agent networks.

---

## 8. Verification & Test Suite

### Backend Test Results (119/119 Passed)
- **Phase 1–3 Regression**: 66/66 passed
- **Phase 4A Regression**: 12/12 passed
- **Phase 4B Regression**: 20/20 passed
- **Phase 4C Regression**: 9/9 passed
- **Phase 4D Agent API**: 12/12 passed (`tests/integration/test_agent_api.py`)
  - `test_agent_chat_unauthenticated_rejected` (401)
  - `test_agent_chat_unauthorized_project_forbidden` (403)
  - `test_agent_chat_mismatched_repository_conflict` (409)
  - `test_agent_chat_direct_answer_non_streaming` (200 JSON)
  - `test_agent_chat_repository_tool_use_with_grounded_sources` (200 JSON with citations)
  - `test_agent_chat_creates_and_reuses_session` (session persistence & reuse)
  - `test_agent_chat_session_ownership_enforced` (403 on cross-user session theft)
  - `test_agent_chat_session_context_mismatch_rejected` (409 on repo switch)
  - `test_agent_chat_sse_streaming_direct_endpoint` (text/event-stream)
  - `test_agent_chat_sse_streaming_with_tool_lifecycle` (tool_call & tool_result events)
  - `test_agent_chat_validation_errors` (422 on empty / oversized message)
  - `test_agent_chat_timeout_handling` (504 on execution timeout)

### Static Analysis & Frontend Build
- **Ruff**: Clean (0 lint errors across 108 source files)
- **Mypy**: Clean (0 type errors across 108 source files)
- **Frontend Vitest**: 9/9 passed
- **Next.js Production Build**: Successful build (11 static pages generated)
