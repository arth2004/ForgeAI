# Phase 4A: Agent Foundation — Technical Documentation

## 1. Purpose

Phase 4A establishes the core agent runtime, state container, and model provider abstraction for **Forge AI**. It introduces a clean, minimal LangGraph execution foundation designed to support future repository-aware agent workflows without prematurely implementing tools, long-term memory, autonomous execution, or UI features.

---

## 2. Architecture

```text
User Input / Query
        │
        ▼
   AgentState  (TypedDict with messages, context, tool_results, metadata)
        │
        ▼
  CompiledStateGraph (LangGraph)
        │
        ▼
   [START Node]
        │
        ▼
   [Agent Node] ──► BaseChatModelProvider ──► (Gemini / OpenAI / Mock)
        │                     ▲
        ▼                     │
   Updated State ◄────────────┘
        │
        ▼
   [END Node]
        │
        ▼
   Final State (final_answer, updated messages)
```

### Architectural Boundaries
- **No Direct Database Queries:** The agent graph has zero dependencies on PostgreSQL, pgvector, SQLAlchemy models, or active sessions.
- **No Retrieval Coupling:** The agent graph does not call Phase 3 retrieval or ingestion services directly.
- **Isolated Provider Layer:** The LangGraph execution logic communicates only with the abstract `BaseChatModelProvider` interface, allowing hot-swapping between Gemini, OpenAI, or deterministic Mock providers.

---

## 3. Components

### A. State Container (`app.agent.state`)
The `AgentState` is a strongly typed schema built on LangGraph's `TypedDict` and `langchain_core.messages`:

| Field | Type | Description |
| :--- | :--- | :--- |
| `user_query` | `str` | Raw user instruction or prompt. |
| `messages` | `Annotated[list[BaseMessage], add_messages]` | Chronological message sequence with LangGraph append reducer. |
| `repository_id` | `str \| None` | Target repository identifier (for future tool scoping). |
| `branch_id` | `str \| None` | Target repository branch identifier. |
| `retrieved_context` | `list[dict[str, Any]]` | Future evidence payload placeholder. |
| `tool_results` | `list[dict[str, Any]]` | Future tool invocation execution log. |
| `final_answer` | `str \| None` | Synthesized final response string. |
| `metadata` | `dict[str, Any]` | Tenant, session, and execution metadata. |

- `create_initial_state(user_query, ...)`: Standardized constructor providing predictable defaults.

### B. Minimal LangGraph Graph (`app.agent.graph`)
- **Topology:** `START -> agent_node -> END`.
- **`agent_node`:** Receives `AgentState`, prepares message history, invokes the injected `BaseChatModelProvider`, logs execution metrics (provider, model, token length), and returns updated state with the assistant message and `final_answer`.
- **`build_agent_graph(model_provider=None)`:** Factory constructing and compiling the `CompiledStateGraph`.

### C. Model Abstraction Layer (`app.agent.models`)
- **`BaseChatModelProvider` (ABC):** Abstract base class exposing `ainvoke(messages: list[BaseMessage]) -> BaseMessage`.
- **`MockChatModelProvider`:** Deterministic provider for zero-API-key testing, failure simulation, and call history assertion.
- **`GeminiChatModelProvider`:** Direct HTTPS integration with Google Gemini chat completions.
- **`OpenAIChatModelProvider`:** Direct HTTPS integration with OpenAI chat completions.
- **`get_chat_model_provider(...)`:** Factory resolving providers from application settings or runtime parameters.
- **`sanitize_secret_text(...)`:** Utility redacting API keys and sensitive tokens before logging or exception propagation.

### D. Agent Configuration (`app.agent.config` & `app.core.config`)
- `AGENT_DEFAULT_PROVIDER`: `"google"` (or `"openai"` / `"mock"`).
- `AGENT_GEMINI_MODEL`: `"gemini-2.5-pro"`.
- `AGENT_OPENAI_MODEL`: `"gpt-4o"`.
- `AGENT_TEMPERATURE`: `0.2`.
- `AGENT_MAX_TOKENS`: `4096`.
- `AGENT_TIMEOUT_SECONDS`: `60.0`.
- `AgentConfig`: Immutable runtime configuration container.

### E. Exception Hierarchy (`app.agent.exceptions`)
- `AgentException(ForgeAIException)`: Base error class (HTTP 500).
- `ModelProviderException(AgentException)`: Raised on upstream LLM failure or timeout (HTTP 502).
- `AgentExecutionException(AgentException)`: Raised on graph node transition errors (HTTP 500).
- `AgentConfigException(AgentException)`: Raised on invalid configuration (HTTP 400).

---

## 4. Explicit Non-Goals for Phase 4A

The following capabilities are strictly deferred to future Phase 4 milestones:
- ❌ **Repository Tools:** No file reading, grep, symbol lookup, or git diff tools in the graph.
- ❌ **Retrieval Coupling:** No RAG queries executed inside the agent node.
- ❌ **Agent Memory:** No database checkpointing or conversational vector memory.
- ❌ **Multi-Agent Orchestration:** No planner/coder/reviewer multi-node graph.
- ❌ **Autonomous Code Modification:** No patch generation or file system writes.
- ❌ **Agent API Endpoints:** No public HTTP `/api/v1/agent/*` routes.
- ❌ **Frontend Agent UI:** No chat panel or streaming UI integration.

---

## 5. Test Suite & Verification

### Test Breakdown
- **Unit Tests (`backend/tests/unit/test_agent_foundation.py`):**
  - `test_agent_state_creation_and_defaults`: Validates state structure and defaults.
  - `test_agent_state_with_custom_messages`: Verifies custom message history preservation.
  - `test_agent_config_from_settings_and_overrides`: Checks configuration factory and overrides.
  - `test_mock_chat_model_provider`: Tests deterministic responses and call history recording.
  - `test_mock_chat_model_provider_failure`: Tests error simulation.
  - `test_get_chat_model_provider_factory`: Validates factory resolution.
  - `test_sanitize_secret_text_redaction`: Verifies API key redaction.
  - `test_agent_exceptions_hierarchy`: Validates HTTP status codes and detail attributes.
- **Integration Tests (`backend/tests/integration/test_agent_graph.py`):**
  - `test_build_and_compile_agent_graph`: Verifies compilation and node topology.
  - `test_agent_graph_execution_with_mock_model`: Verifies end-to-end `START -> agent -> END` flow.
  - `test_agent_graph_handles_provider_failure`: Verifies exception wrapping and secret redaction.
  - `test_phase_4a_architectural_boundary_static_check`: Enforces zero forbidden imports from database or Phase 3 services.

### Test Results
- **Backend Pytest:** **78/78 passed** (66 baseline Phase 3 tests + 12 Phase 4A tests).
- **Frontend Vitest:** **9/9 passed**.
- **Frontend Next.js Build:** **Compiled successfully**.
- **Linter (Ruff):** **0 errors** across all source and test files.
- **Type Checker (Mypy):** **0 errors** across 72 source files.
