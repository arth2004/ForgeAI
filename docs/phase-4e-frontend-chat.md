# Phase 4E — Frontend Chat Integration

## 1. Purpose

Phase 4E delivers the interactive frontend chat interface for Forge AI, allowing authenticated developers to engage in repository-grounded conversations directly from the project workspace. The interface communicates seamlessly with the Phase 4D public agent chat API, handling real-time Server-Sent Events (SSE) streaming, progressive tool activity rendering, grounded source citations, and robust error recovery.

---

## 2. UI Architecture

```
                       +-----------------------------------+
                       |      ProjectWorkspacePage         |
                       | (app/(dashboard)/projects/[id])   |
                       +-----------------------------------+
                                         |
                                         v
                       +-----------------------------------+
                       |           AgentChat               |
                       |    (components/agent/AgentChat)   |
                       +-----------------------------------+
                                         |
                                         v
                       +-----------------------------------+
                       |         useAgentChat Hook         |
                       |      (hooks/useAgentChat.ts)      |
                       +-----------------------------------+
                                         |
                                         v
                       +-----------------------------------+
                       |         agent-api Client          |
                       |       (lib/agent-api.ts)          |
                       +-----------------------------------+
                                         |
                       POST /api/v1/agent/chat/stream
                                         |
                                         v
                       +-----------------------------------+
                       |    Phase 4D Public Agent API      |
                       +-----------------------------------+
```

---

## 3. Component Hierarchy

```
AgentChat
├── Header (Repository & Branch Context, Active Session ID, Reset Action)
├── Global Error Banner (When top-level error occurs)
├── AgentMessageList
│    ├── AgentEmptyState (When message history is empty)
│    └── AgentMessage[]
│         ├── User Message (Bubble aligned right)
│         └── Assistant Message (Card aligned left)
│              ├── AgentActivity (Progressive tool execution indicator)
│              ├── Answer Content (Markdown-formatted text)
│              ├── AgentSources (Grounded citation cards with copy helpers)
│              └── Error Banner (When turn failed)
└── AgentComposer (Auto-resizing textarea, Shift+Enter newline, Send / Cancel stream)
```

---

## 4. Session Handling

1. **Context Resolution**: When starting a new conversation, `session_id` is omitted in the initial request payload. The backend creates an `AgentSession` model binding `user_id`, `project_id`, `repository_id`, and `branch_id`.
2. **Session ID Binding**: The frontend receives `session_id` on the `session.created` (or `agent.completed`) SSE event and stores it in React component state.
3. **Session Reuse**: All subsequent messages within the conversation send `session_id`, ensuring persistent operational context without mutating repository ownership.
4. **Session Reset**: Clicking the "Reset" button aborts any running stream, clears the message history, and discards the active `session_id`.

---

## 5. SSE Event Mapping to UI State

| SSE Event | Frontend Action | UI Presentation |
| :--- | :--- | :--- |
| **`session.created`** | Updates `sessionId` state. | Header displays `session: <prefix>...` |
| **`agent.started`** | Sets assistant message status to `"streaming"`. | "Reasoning" spinner indicator appears. |
| **`agent.tool_call`** | Appends a new `AgentToolActivity` entry with status `"running"`. | Shows action badge (e.g. "Searching repository codebase..."). |
| **`agent.tool_result`** | Updates matching tool activity to `"success"` or `"failed"`. | Displays checkmark and duration (e.g. "✓ done (45ms)"). |
| **`agent.completed`** | Updates assistant message content, extracts `sources`, and marks `"completed"`. | Renders answer text, citation cards, and enables new input. |
| **`agent.error`** | Sets assistant message status to `"error"`, stops stream. | Renders user-friendly error banner. |

---

## 6. Error Handling

Standard HTTP status codes and stream errors are mapped to developer-friendly notifications:
- **401**: *"Your session has expired. Please sign in again."*
- **403**: *"You do not have permission to access this project or repository."*
- **404**: *"The requested project, repository, or branch was not found."*
- **409**: *"This conversation is bound to a different repository context."*
- **422**: *"Invalid message payload. Please verify your query length."*
- **429**: *"Forge AI is temporarily rate-limited. Please try again shortly."*
- **504**: *"The agent took too long to respond. Try asking a more specific question."*

---

## 7. Cancellation Semantics

- While streaming, the Composer replaces the **Send** button with a **Stop** button.
- Clicking Stop invokes `abortController.abort()`, cleanly closing the underlying HTTP request and `ReadableStream`.
- Existing message history and any completed partial answers are preserved.

---

## 8. Non-Goals (Scope Boundaries)

Phase 4E strictly does NOT implement:
- Long-term cross-session memory in localStorage or database chat history.
- Model selection or LLM temperature controls.
- Autonomous repository file editing or mutation.
- Shell execution, CLI commands, or sandboxed code runs.
- GitHub pull request or commit creation.
- Model Context Protocol (MCP) servers or multi-agent hierarchies.

---

## 9. Verification & Test Suite

### Frontend Vitest Results (18/18 Passed)
- **Baseline Tests (9/9 passed)**:
  - `app-shell.test.tsx` (4 tests)
  - `github-wizard.test.tsx` (2 tests)
  - `retrieval-and-project.test.tsx` (3 tests)
- **Phase 4E Tests (9/9 passed)** (`tests/agent-chat.test.tsx`):
  - Renders empty state with sample prompt suggestions and header info
  - Sends message when clicking a sample prompt suggestion
  - Handles tool lifecycle events and renders AgentActivity badges
  - Supports stopping / cancelling an ongoing stream via AbortController
  - Renders user-friendly error on agent API failure (403)
  - Clears conversation when clicking Reset button
  - Parses multiple SSE events in a single network chunk
  - Handles a single SSE event split across multiple network chunks
  - Correctly maps standard HTTP status codes to user-facing messages

### Backend Regression Results (119/119 Passed)
- Phase 1–3: 66/66 passed
- Phase 4A: 12/12 passed
- Phase 4B: 20/20 passed
- Phase 4C: 9/9 passed
- Phase 4D: 12/12 passed
- **Total Backend**: 119/119 passed
- **Ruff & Mypy**: Clean across 108 source files
- **Next.js Production Build**: Clean build (all static & dynamic pages compiled)
