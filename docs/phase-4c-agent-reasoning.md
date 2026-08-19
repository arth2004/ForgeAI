# Phase 4C — Agent Reasoning & Tool-Use Loop

## 1. Purpose

Phase 4C establishes the **Agent Reasoning & Tool-Use Loop** for Forge AI. Building upon the Phase 4A Agent Foundation and Phase 4B Repository Tool Layer, Phase 4C enables the agent to dynamically reason over user questions, decide when and which repository tools to execute, perform bounded multi-step investigations, accumulate structured evidence, and synthesize grounded final answers without hallucination.

---

## 2. Reasoning Loop Architecture

```
                             +-----------------------+
                             |     User Question     |
                             +-----------------------+
                                         |
                                         v
                             +-----------------------+
                             |      agent_node       | <----+
                             | (Model Reason & Plan) |      |
                             +-----------------------+      |
                                         |                  |
                                         v                  |
                             +-----------------------+      |
                             |      tool_router      |      |
                             +-----------------------+      |
                               /                   \        |
                 tool_calls > 0                     no tool_calls / max iter
                             /                       \
                            v                         v
                 +--------------------+            +-----+
                 |     tools_node     | ---------> | END |
                 | (Execute & Observe)|            +-----+
                 +--------------------+
```

### Execution Flow:
1. **User Question Ingestion**: The agent receives the prompt and ensures system reasoning instructions are active.
2. **Direct Answer vs. Tool Decision**: If the inquiry is conversational or general knowledge (e.g. "What is Forge AI?"), the agent answers directly without unnecessary tool calls (0 tool calls, 1 iteration).
3. **Repository Tool Selection**: For codebase-specific questions, the agent selects from the tool registry (`search_repository`, `search_symbol`, `get_file`).
4. **Execution & Observation**: `tools_node` executes the requested tools asynchronously against the database session, validates parameters, and appends `ToolMessage` observations.
5. **Evidence Accumulation**: Extracted code chunks, symbol declarations, and file windows are accumulated in `retrieved_context` across turns without overwriting earlier evidence.
6. **Multi-Step Investigation**: The agent can perform multi-turn evidence gathering (e.g. search broad repo $\rightarrow$ search symbol declaration $\rightarrow$ read specific file range).
7. **Grounded Final Response**: The model synthesizes a factual conclusion referencing specific files and symbols, halting safely at `END`.

---

## 3. Tool Selection Guidelines

The model selects tools dynamically based on the user's question and current evidence:

| Tool | Primary Use Case | Example Query | Output Evidence |
| :--- | :--- | :--- | :--- |
| **`search_repository`** | Broad conceptual discovery, finding implementation files, cross-codebase feature searches. | *"Where is hybrid retrieval implemented?"* | Ranked code & doc chunks with RRF scores, file paths, line ranges, and commit SHAs. |
| **`search_symbol`** | Locating specific class, function, method, or interface declarations from indexed AST records. | *"Find GeminiEmbeddingProvider symbol"* | Symbol declarations, AST chunk types (`CLASS`, `METHOD`), start/end lines, context headers. |
| **`get_file`** | Reading specific file implementations or inspecting precise line windows after discovery. | *"Read lines 15-60 of hybrid.py"* | File content slice, line range window, chunk metadata (bounded to 16KB). |

---

## 4. Operational Limits & Guardrails

To prevent infinite loops, context window exhaustion, and excessive load, Phase 4C enforces strict, layered constraints:

1. **Maximum Iteration Guard (`MAX_AGENT_ITERATIONS = 5`)**:
   - Hard cap on agent $\leftrightarrow$ tool cycles per execution graph run.
   - Configurable per-run via `AgentConfig` or `RunnableConfig` overrides.
   - Prevents endless search loops even if a model behaves adversarially.
2. **Tool Usage Guard (`ToolUsageGuard`)**:
   - Limits total tool calls per execution (default 10) and per-tool invocations (default 6).
   - Rejects excess calls with structured `ToolRateLimitError` (HTTP 429).
3. **Output Size Thresholds**:
   - Tool outputs are truncated at 24KB (16KB for file content) with clear `[TRUNCATED]` markers.
4. **Timeout Enforcement**:
   - Model provider calls enforce configurable timeouts (default 60s).

---

## 5. Grounding & Anti-Hallucination

- **Evidence-Based Answers**: All repository claims must be backed by evidence returned in `retrieved_context`. Answers cite exact file paths and symbol names.
- **Insufficient Evidence Handling**: When a searched component does not exist (e.g. *"Where is the Stripe payment gateway implemented?"*), the agent reports that no matching implementation was found in the indexed repository rather than inventing files or logic.
- **Privacy & Hygiene**: Chain-of-thought tokens, raw prompts, and JSON RPC envelopes are never exposed in final user-facing answers.

---

## 6. Tool Failure Recovery

When a tool encounters an error (e.g. non-existent file or malformed query):
1. `tools_node` catches the exception, sanitizes secret tokens, and returns a structured error envelope in `ToolMessage`.
2. The agent receives the error, analyzes the failure, and chooses whether to:
   - Try an alternate tool (e.g. switch from `get_file` to `search_symbol`).
   - Answer using existing gathered evidence.
   - Inform the user that the requested resource could not be found.

---

## 7. Structured Observability & Logging

Phase 4C emits structured events for monitoring execution lifecycle:
- `[agent.execution.started]`: Logged on turn 1 with provider, model, query length, and message count.
- `[agent.tool.requested]`: Logged when the model outputs tool calls with tool name and call ID.
- `[agent.tool.completed]`: Logged when a tool finishes with `duration_ms` and `success=True`.
- `[agent.tool.failed]`: Logged on tool errors with `duration_ms` and sanitized error text.
- `[agent.execution.completed]`: Logged on final answer generation with total iterations, duration, response length, and accumulated context count.
- `[agent.execution.limit_reached]`: Logged when `MAX_AGENT_ITERATIONS` is hit.

---

## 8. Non-Goals (Strict Phase 4C Scope Boundaries)

In strict accordance with the Phase 4 roadmap, Phase 4C does **NOT** include:
- Public agent API endpoints (deferred to Phase 4D).
- Frontend chat UI or WebSocket streaming.
- Persistent conversation history or long-term memory across sessions.
- Autonomous coding, file editing, or repository mutation.
- Shell execution, CLI commands, or sandboxed execution environments.
- GitHub write operations, issue creation, or pull request generation.
- Model Context Protocol (MCP) servers or multi-agent supervisor hierarchies.

---

## 9. Verification & Test Suite

### Backend Test Results (107/107 Passed)
- **Phase 1–3 Baseline**: 66/66 passed
- **Phase 4A Agent Foundation**: 12/12 passed
- **Phase 4B Repository Tools**: 20/20 passed
- **Phase 4C Reasoning Loop**: 9/9 passed (`tests/integration/test_agent_reasoning_loop.py`)
  - Direct answer path (0 tool calls, 1 iteration)
  - Single-step tool selection & grounding (`search_repository` $\rightarrow$ final answer)
  - Multi-step investigation & accumulation (`search_repo` $\rightarrow$ `search_symbol` $\rightarrow$ `get_file`)
  - Insufficient evidence & anti-hallucination handling
  - Tool failure recovery & fallback
  - Maximum iteration limit guard (halts at 5)
  - Custom iteration limit override (halts at 3)
  - `ToolUsageGuard` rate limit enforcement
  - Structured observability logging verification

### Static Analysis & Frontend Build
- **Ruff**: Clean (0 errors across 103 source files)
- **Mypy**: Clean (0 errors across 103 source files)
- **Frontend Vitest**: 9/9 passed
- **Next.js Build**: Successful production build (11 static pages)
