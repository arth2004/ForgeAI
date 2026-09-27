# PHASE 7C — REAL AI RUNTIME AUDIT

**Repository:** `ForgeAi`
**HEAD:** `c174e38 fix(ui): clean up template literal in AgentPlanView`
**Audit type:** READ-ONLY DIAGNOSTIC. Zero source files, tests, schemas, migrations, routes, components, environment files, or Docker configuration were modified.
**Date:** 2026-08-26

---

## 1. Executive Summary

**VERDICT: PARTIALLY REAL**

Forge AI is not a mock application wearing a real costume, and it is not a real application either. It is a real application with **two real model call sites** and a **fabrication layer wrapped around them** that makes it impossible to tell, from the outside, whether a real model ran.

What is genuinely real:

- The provider layer is real. `GeminiChatModelProvider` and `OpenAIChatModelProvider` in `backend/app/agent/models.py` are hand-written `httpx` clients that speak real HTTP to real vendor endpoints. They parse real tool-call responses, implement 429 retry with `Retry-After` extraction, and sanitize secrets out of error text.
- The retrieval engine is real. `HybridSearchEngine` in `backend/app/services/retrieval/hybrid.py` performs genuine dense pgvector cosine search plus sparse `ts_rank_cd` full-text search fused with RRF. The ingestion pipeline genuinely parses files with tree-sitter, chunks by AST, and calls a real Gemini embedding endpoint.
- The LangGraph reasoning loop is real. `build_agent_graph` in `backend/app/agent/graph.py` wires a genuine agent ⇄ tools cycle, and `tools_node` genuinely executes the 11 registered tools and genuinely feeds their output back to the model as `ToolMessage` content.
- Credentials are present. `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENAI_API_KEY` are all **CONFIGURED**.

What makes it only partially real:

1. **The chat provider and the embedding provider are two independent, uncoordinated configurations.** The active chat provider is Groq (`AGENT_DEFAULT_PROVIDER=groq`), while embeddings are pinned to Google (`EMBEDDING_PROVIDER=google`) with a model identifier (`gemini-embedding-2`) that this audit could not verify exists. There is **no mock, offline, or fallback embedding provider anywhere in the repository**. If the Gemini embedding endpoint rejects that model name, retrieval returns no context, `search_repository` raises, the error is handed to the model as a tool result, and the model answers from its own priors — producing a fluent, confident, ungrounded answer. This is the precise mechanism behind the reported symptom "works with mocks, cannot be reliably exercised with a real model."
2. **`MockChatModelProvider` ships inside the production module** `app/agent/models.py` and is selectable at runtime via a single environment variable. `.env.example` ships with `AGENT_DEFAULT_PROVIDER=mock`, so a clean checkout defaults to a fabricating model that returns a hardcoded `ImplementationPlan` naming `app/api/v1/agent.py`.
3. **Two of the four multi-agent roles never call a model at all.** `CoderAgent` and `TesterAgent` accept a `model_provider` argument and never invoke it. They fabricate a diff and a passing test run respectively. `EngineeringOrchestrator`, which would coordinate them, is never constructed anywhere in `app/` — `POST /api/v1/agent/tasks` inserts a database row and returns.
4. **The frontend fabricates every artifact downstream of the plan** — patch diff, workspace, test run, commit SHA, and pull request URL — with no flag to disable it, and the guards intended to prevent this fail open because `AgentMessage.tsx` passes the literal string `"mock-approval-123"` where a UUID is expected.
5. **Token streaming does not exist.** No provider implements `astream`. The frontend's 38-member event union contains zero token/delta events. The answer is written to the UI exactly once, on `agent.completed`.

Demo readiness with a real model, today:

| Demo | Scenario | Classification |
| --- | --- | --- |
| A | "Explain the authentication architecture of this repository." | **PARTIALLY WORKS** — real model reasoning runs, but grounding depends on an unverified embedding model; on embedding failure the answer is ungrounded and indistinguishable from a grounded one |
| B | "Find potential race conditions in this repository." | **PARTIALLY WORKS** — same as A, and additionally limited by `MAX_AGENT_ITERATIONS = 5` and by only 3 of 11 tools being declared to the model |
| C | GitHub PR review from a real webhook | **PARTIALLY WORKS / MOCKED** — webhook verification, snapshot, diff extraction, AST context, and the ReviewerAgent model call are real; but GitHub diff-fetch failure silently substitutes a **hardcoded synthetic diff**, and any model response parse failure silently yields **"APPROVED, zero findings"** |

No scenario is `BLOCKED` in the sense of raising a hard error. That is the danger: every failure mode in this system degrades into a plausible-looking success.

---

## 2. Current AI Runtime Architecture

### 2.1 Path 1 — Repository chat (the primary AI path)

```
User types in browser
  → frontend/src/components/agent/AgentChatPanel.tsx
  → frontend/src/hooks/useAgentChat.ts :: sendMessage()            [AbortController @115]
  → frontend/src/lib/agent-api.ts :: streamAgentMessage()          [@189-230, stream:true @204,207]
  → POST /api/v1/agent/chat/stream
  → backend/app/api/v1/agent.py                                   [27 routes]
  → backend/app/services/agent_service.py :: AgentService.stream_chat()   [@287]
      · _format_sse(event_type, payload)                          [@295-296]
      · emits session.created, agent.started
  → backend/app/agent/graph.py :: build_agent_graph()             [@306]
      START → agent → tool_router → {tools → agent, END}
      MAX_AGENT_ITERATIONS = 5
  → backend/app/agent/graph.py :: agent_node()                    [@37]
      provider = override
                 ?? config["configurable"]["model_provider"]
                 ?? get_chat_model_provider()                     [@55  ← production call site 1 of 2]
      await provider.ainvoke(messages)                             [@90]
  → backend/app/agent/models.py :: get_chat_model_provider()       [@784]
      prov = (provider or settings.AGENT_DEFAULT_PROVIDER).lower().strip()
      mock → MockChatModelProvider                                [@140]
      openai | groq | openai_compatible → OpenAIChatModelProvider  [@525]
      google | gemini → GeminiChatModelProvider                    [@259]
      else → ModelProviderException
  → HTTP POST {GROQ_BASE_URL}/chat/completions                    [models.py @672]
      payload always includes "tools": self._get_openai_tools_declaration()  [@552]
  ── model returns tool_calls ──
  → backend/app/agent/graph.py :: tool_router()                   [@139]
  → backend/app/agent/graph.py :: tools_node()                    [@164]
      get_agent_tool_by_name(name) over 11 tools
      → backend/app/agent/tools/repository_search.py :: RepositorySearchTool.aexecute()  [@?]
      → backend/app/services/retrieval/hybrid.py :: HybridSearchEngine.search()          [@393]
          · resolve ACTIVE RepositoryIndexVersion; if none → return []
          · embed_provider = get_embedding_provider()
          · query_vector = await embed_provider.embed_query(query)
            → backend/app/services/embedding/gemini.py :: GeminiEmbeddingProvider
              HTTP POST {BASE_URL}/models/{model}:batchEmbedContents?key=…
          · dense:  ChunkEmbedding.embedding.cosine_distance(query_vector)  [pgvector HNSW]
                    OR python_cosine_distance()                            [@356, SQLite branch]
          · sparse: func.ts_rank_cd(CodeChunk.search_vector, plainto_tsquery)
          · fuse:   RRF k=60
      ← truncate_tool_output(chunk.content, max_chars=4000)
      → ToolMessage(content=json.dumps(res.model_dump()))          [graph.py @233]
        ↑ THIS is the only mechanism by which retrieved code reaches the model prompt
  ── loop back to agent_node, max 5 iterations ──
  → graph.astream(initial_state, stream_mode="updates")           [agent_service.py @357]
      emits agent.tool_call, agent.tool_result
      emits agent.completed carrying the ENTIRE answer               [@436-446]
  → frontend/src/lib/agent-api.ts :: parseSSEStream()              [@70-147]
  → frontend/src/hooks/useAgentChat.ts case "agent.completed":      [@185-201]
      content: data.answer || "Answer generated."                   [@194]
  → frontend/src/components/agent/AgentMessage.tsx
```

### 2.2 Path 2 — GitHub PR review (Phase 7B)

```
GitHub App delivers webhook
  → POST /api/v1/github/webhooks
  → backend/app/api/v1/github_webhooks.py
      verify_github_webhook_signature()  HMAC-SHA256                [@63]
      delivery-ID dedup                                             [@82]
      if settings.ENVIRONMENT != "test":
          background_tasks.add_task(_run_pr_review_background, str(review_task.id))  [@106-107]
          ↑ str passed to a uuid.UUID-annotated parameter
          ↑ test-env gate means NO test ever exercises dispatch
  → _run_pr_review_background()  → FastAPI BackgroundTasks (NOT ARQ)
  → backend/app/services/github/pr_ingestion_service.py  → immutable PullRequestSnapshot
  → backend/app/services/github/diff_context_service.py  → scoped diff + AST symbol expansion
  → backend/app/services/github/sanitizer.py :: sanitize_pr_text / wrap_untrusted_content
  → backend/app/services/github/pr_review_service.py :: PRReviewService.execute_review()
      · GitHub diff fetch; on ANY failure:
        logger.info("Could not fetch remote PR diff from GitHub (%s). Proceeding with synthetic fallback.")
        diff_text = f"--- a/{repo_name}/core.py\n+++ …\n+    # Refactored token calculation\n+    return 1\n"
      · provider = model_provider or get_chat_model_provider()      [@120 ← production call site 2 of 2]
      · SHA drift check wrapped in: except Exception: logger.debug("Skipping live SHA check …")
  → backend/app/agent/multi_agent/reviewer.py :: ReviewerAgent.execute()
      · REVIEWER_SYSTEM_PROMPT demands strict JSON                  [@25]
      · response = await self.model_provider.ainvoke(messages)      [@78  ← REAL model call]
      · strip ```json fences → json.loads → ReviewFindingSchema
      · except Exception: logger.info("Using default clean review output …")
        with pre-initialised review_status = "APPROVED", zero findings
  → PostgreSQL: ReviewFinding rows + PullRequestReviewTask counters
  → GET /api/v1/github/pulls/…
  → frontend/src/components/agent/PullRequestReviewCard.tsx
```

### 2.3 Path 3 — Multi-agent engineering (DEAD)

```
POST /api/v1/agent/tasks        [backend/app/api/v1/agent.py ~@578]
  docstring: "Initializes a multi-agent engineering task managed by the EngineeringOrchestrator"
  actual body: INSERT AgentSession + AgentTask (active_agent="SUPERVISOR"), commit, return
  → NO orchestrator constructed. NO graph. NO model call.

backend/app/agent/multi_agent/orchestrator.py :: EngineeringOrchestrator   [@?]
  · requires 4 explicit providers in __init__
  · builds supervisor StateGraph: planner → coder → tester → reviewer → supervisor_guard
  · _route_next_step() implements 5 human approval gates                    [@110]
  · NEVER CONSTRUCTED ANYWHERE IN app/  — only re-exported and named in a docstring

backend/app/agent/multi_agent/config.py :: role_provider_config
  · reads raw os.getenv at import time (bypasses pydantic-settings .env loading entirely)
  · defaults: planner=gemini, coder=openai, tester=groq, reviewer_model=gemini-2.5-pro
  · NEVER CONSUMED — dead code
```

### 2.4 Memory

There is no conversational memory subsystem. There is no LangGraph checkpointer configured (`langgraph-checkpoint==4.2.0` is present in the lock file as a transitive dependency but is not wired). Conversation continuity is provided by `AgentSession` / `AgentMessage` rows in PostgreSQL, re-hydrated into the message list per request. Within a single graph execution, state is the LangGraph `AgentState` dict only.

---

## 3. Real vs Mock Matrix

| Component | Production Path | Real/Mock | File | Symbol | Notes |
| --- | --- | --- | --- | --- | --- |
| LLM — Gemini | YES | **REAL** | `backend/app/agent/models.py` | `GeminiChatModelProvider` (@259), `ainvoke` (@418) | Hand-rolled `httpx` client to `v1beta:generateContent`. No vendor SDK. Model `gemini-3.1-pro-preview` UNVERIFIED. |
| LLM — OpenAI/Groq/compatible | YES | **REAL** | `backend/app/agent/models.py` | `OpenAIChatModelProvider` (@525), `ainvoke` (@672) | One class serves 3 provider names. Active path (`groq`). Always sends `tools`. |
| LLM — Mock | **YES (selectable)** | **MOCK** | `backend/app/agent/models.py` | `MockChatModelProvider` (@140), `ainvoke` (@165) | Ships in the production module. Reachable via `AGENT_DEFAULT_PROVIDER=mock`, which is what `.env.example:59` sets. Fabricates a hardcoded `ImplementationPlan`. |
| Provider factory | YES | **REAL** | `backend/app/agent/models.py` | `get_chat_model_provider` (@784) | Only 2 production call sites. Never passes `timeout_seconds`, so `AGENT_TIMEOUT_SECONDS` never reaches a provider. |
| Embeddings — Gemini | YES | **REAL** | `backend/app/services/embedding/gemini.py` | `GeminiEmbeddingProvider`, `_embed_batch_with_retry` | Real `batchEmbedContents` call. API key in URL query string. 404 is NOT retried and surfaces as opaque 502. |
| Embeddings — factory | YES | **REAL (unsafe default)** | `backend/app/services/embedding/factory.py` | `get_embedding_provider` (@15-17) | `google`→Gemini, `openai`→OpenAI, **any other value silently → Gemini**. No mock/offline provider exists anywhere. |
| Embeddings — mock/offline | — | **ABSENT** | — | — | There is no fake, deterministic, or local embedding provider in the repository. Embeddings are a hard network dependency. |
| Retrieval — dense | YES | **REAL** | `backend/app/services/retrieval/hybrid.py` | `HybridSearchEngine._execute_search` | `ChunkEmbedding.embedding.cosine_distance(query_vector)`, limit 60, pgvector HNSW cosine. |
| Retrieval — dense (SQLite) | test only | **REAL algorithm, no index** | `backend/app/services/retrieval/hybrid.py` | `python_cosine_distance` (@356) | Loads every `ChunkEmbedding` row and scores in pure Python. This is the branch all tests take. |
| Retrieval — sparse | YES | **REAL** | `backend/app/services/retrieval/hybrid.py` | `func.ts_rank_cd(...)` | Wrapped in `try/except` logging `"Full-text search fallback: {e}"` — degrades silently. |
| Retrieval — fusion | YES | **REAL** | `backend/app/services/retrieval/hybrid.py` | RRF, k=60 | Genuine reciprocal-rank fusion over dense + sparse + symbol. |
| Ingestion / chunking | YES | **REAL** | `backend/app/services/ingestion/engine.py` | `IngestionEngine.run_indexing` (@81), `CodeChunker.parse_and_chunk_file` (@251) | Real tree-sitter AST chunking; `text_to_embed = context_header + content` (@294); real `embed_documents` (@394). |
| pgvector storage | YES | **REAL** | `backend/alembic/versions/0004_repo_intelligence.py` | `Vector(768)` (@175), `ix_chunk_embeddings_hnsw` (@200-201) | Real HNSW `vector_cosine_ops` index. Never exercised by any test. |
| LangGraph | YES | **REAL** | `backend/app/agent/graph.py` | `build_agent_graph` (@306), `agent_node` (@37), `tool_router` (@139), `tools_node` (@164) | Genuine `StateGraph` compile and cycle. `MAX_AGENT_ITERATIONS = 5`. |
| Tools — registry | YES | **REAL** | `backend/app/agent/tools/__init__.py` | `get_agent_tools`, `get_agent_tool_by_name` | 11 real tools, all with real implementations. |
| Tools — declaration to model | YES | **MOCK (hardcoded subset)** | `backend/app/agent/models.py` | `_get_gemini_tools_declaration` (@279), `_get_openai_tools_declaration` (@552) | Hand-written JSON declaring only 3 tools (`search_repository`, `search_symbol`, `get_file`). **Not derived from the registry.** 8 of 11 tools are invisible to the model. |
| Tool execution | YES | **REAL** | `backend/app/agent/graph.py` | `tools_node` (@164), `ToolMessage` (@233) | Real dispatch, real results, real feedback into the prompt. |
| Memory | YES | **N/A — none** | `backend/app/models/agent.py` | `AgentSession`, `AgentMessage` | DB-persisted transcript only. No checkpointer, no summarisation, no vector memory. |
| Streaming — backend | YES | **BUFFERED (C)** | `backend/app/services/agent_service.py` | `stream_chat` (@287), `_format_sse` (@295) | Real SSE transport, but `stream_mode="updates"` emits node-completion events. Full answer in one `agent.completed` frame (@436-446). |
| Streaming — provider | — | **UNSUPPORTED (D)** | `backend/app/agent/models.py` | `BaseChatModelProvider` (@120) | The ABC declares only `ainvoke` (@135). **No `astream` on any provider.** No provider requests `stream: true`. |
| Streaming — frontend | YES | **BUFFERED (C)** | `frontend/src/hooks/useAgentChat.ts` | `case "agent.completed"` (@185-201) | Only assignment to `msg.content` in the whole streaming path is @194. No `content + delta` anywhere. |
| ReviewerAgent | YES | **REAL model call, MOCK failure mode** | `backend/app/agent/multi_agent/reviewer.py` | `ReviewerAgent.execute` (@78) | Genuine `ainvoke`. But any parse failure → silent `"APPROVED"` + zero findings. |
| PlannerAgent | reachable only via orchestrator (dead) | **REAL model call, MOCK fallback** | `backend/app/agent/multi_agent/planner.py` | `ainvoke` (@102), fallback (@116-125) | Parse failure synthesises an empty `ImplementationPlan`. |
| CoderAgent | dead | **MOCK** | `backend/app/agent/multi_agent/coder.py` | `CoderAgent` (@34 accepts provider) | **Contains no `ainvoke` call at all.** Fabricates `"+# Verified implementation"` diff against `app/api/v1/agent.py`. |
| TesterAgent | dead | **MOCK** | `backend/app/agent/multi_agent/tester.py` | `TesterAgent` | **Contains no `ainvoke` call at all.** Fabricates `status: "PASSED"`, `"1 passed in 0.42s"`. |
| EngineeringOrchestrator | **NO — unreachable** | REAL code, DEAD | `backend/app/agent/multi_agent/orchestrator.py` | `EngineeringOrchestrator` | Never constructed in `app/`. `POST /agent/tasks` only inserts a row. |
| `role_provider_config` | **NO — unreachable** | DEAD | `backend/app/agent/multi_agent/config.py` | `RoleProviderConfig` | Raw `os.getenv` at import time; bypasses `.env`; never consumed. |
| GitHub PR reviewer — webhook | YES | **REAL** | `backend/app/api/v1/github_webhooks.py` | `verify_github_webhook_signature` (@63), dedup (@82) | Real HMAC-SHA256, real replay protection. |
| GitHub PR reviewer — diff | YES | **REAL with MOCK fallback** | `backend/app/services/github/pr_review_service.py` | `execute_review` | On any GitHub fetch failure, substitutes a **hardcoded synthetic diff** and continues as if real. |
| GitHub PR reviewer — SHA drift | YES | **REAL, silently skippable** | `backend/app/services/github/pr_review_service.py` | SHA check | `except Exception: logger.debug("Skipping live SHA check in offline/test mode: %s")`. |
| GitHub mutation | YES | **READ-ONLY (verified)** | `backend/app/services/github/client.py` | — | No PR comment/review POST on the review path. Guarantee holds. |
| Frontend — patch diff | **YES** | **MOCK** | `frontend/src/components/agent/AgentPlanView.tsx` | `MOCK_DIFF_CONTENT` (@13-25), `getMockPatch` (@27-44) | Hardcoded rate-limiter diff, `patch_id: "patch-mock-ratelimit-1"`. Rendered unconditionally @312. |
| Frontend — workspace | **YES** | **MOCK** | `frontend/src/components/agent/AgentPlanView.tsx` | `handleApprove` else-branch (@112-127) | Invents `ws-mock-workspace-1`, `/tmp/forge_workspaces/mock_ws_8bf755`, `base_commit_sha: "e1c144f8b2d41"`. No backend call. |
| Frontend — approval guard | **YES** | **FAILS OPEN** | `frontend/src/components/agent/AgentMessage.tsx` | @135 | `approvalId={message.approvalId \|\| "mock-approval-123"}` — not a UUID, so `isUUID()` fails and control enters the fabricating branch. |
| Frontend — test run | **YES** | **MOCK** | `frontend/src/components/agent/AgentDiffView.tsx` | @288-303 | Fabricates `"1 passed in 0.42s"` — the identical string `TesterAgent` fabricates. |
| Frontend — commit / PR URL | **YES** | **MOCK** | `frontend/src/components/agent/AgentDiffView.tsx` | @321-344 | Fabricates `commit_sha: "405e0329a174f"` and `github_pr_url: ".../pull/1"`. |
| Frontend — git panel | **YES** | **MOCK** | `frontend/src/components/agent/AgentGitPanel.tsx` | @43, @56/91/125 vs @73/107/143 | Falls back to `"mock-workspace-id"`; handlers gated on `isUUID` but status set to COMMITTED/PUSHED/CREATED unconditionally. |
| ARQ worker AI task | **NO** | ABSENT | `backend/app/workers/main.py` | `functions` (@25) | Only `health_check_job`, `index_repository_task`. **No AI/review task registered.** PR review runs in the web process via `BackgroundTasks`. |

---

## 4. Real Model Provider Status

Secrets are reported only as `CONFIGURED` / `MISSING`. No secret value was read into context or printed.

| Provider | Model | Configured | Reachable | Working | Failure |
| --- | --- | --- | --- | --- | --- |
| `groq` (**ACTIVE** — `.env` `AGENT_DEFAULT_PROVIDER=groq`) | `openai/gpt-oss-120b` via `GROQ_BASE_URL=https://api.groq.com/openai/v1` | **CONFIGURED** (`GROQ_API_KEY`) | **UNKNOWN** | **UNKNOWN** | Not exercised — audit sandbox has no network egress. Code path is complete and correct. |
| `google` / `gemini` | `gemini-3.1-pro-preview` | **CONFIGURED** (`GEMINI_API_KEY`) | **UNKNOWN** | **UNKNOWN** | Model identifier **UNVERIFIED** — could not reach `ai.google.dev` (egress blocked). If invalid, `ainvoke` raises `ModelProviderException` with the upstream status. |
| `openai` | `gpt-4o` | **CONFIGURED** (`OPENAI_API_KEY`) | **UNKNOWN** | **UNKNOWN** | Not the active provider. Path shares `OpenAIChatModelProvider`. |
| `openai_compatible` | `OPENAI_COMPATIBLE_MODEL` empty | **MISSING** (`OPENAI_COMPATIBLE_API_KEY` present but empty; `OPENAI_COMPATIBLE_BASE_URL` empty) | NO | NO | **ENVIRONMENT / CREDENTIAL ISSUE** — provider is unconfigured by design. Would fail at request time with an empty base URL. |
| `mock` | — | N/A | YES | YES (fabricates) | Not a failure — but `.env.example:59` ships `AGENT_DEFAULT_PROVIDER=mock`, so any clean checkout runs fabricated output. |
| **Embeddings — `google`** (ACTIVE) | `gemini-embedding-2`, `outputDimensionality=768` | **CONFIGURED** (`GEMINI_API_KEY`) | **UNKNOWN** | **UNKNOWN** | Model identifier **UNVERIFIED**. A 404 falls into the non-retry `else` branch and surfaces as `ForgeAIException(status_code=502)` `"Gemini embedding API error (404): …"`. |
| **Embeddings — `openai`** | `text-embedding-3-small` | **CONFIGURED** (`OPENAI_API_KEY`) | **UNKNOWN** | **UNKNOWN** | Not active. Note: `text-embedding-3-small` native dimension is 1536; the schema is `Vector(768)`. Switching providers without dimension reduction would violate the column type. |
| Local models (Ollama etc.) | — | **ABSENT** | NO | NO | No local provider exists. Not installed, per instruction. |

Three different values of `AGENT_DEFAULT_PROVIDER` coexist in the repository, which is the single largest source of "it worked yesterday" confusion:

| Source | Value |
| --- | --- |
| `backend/app/core/config.py:120` (in-code default) | `google` |
| `.env.example:59` (shipped template) | `mock` |
| `.env` (actual local) | `groq` |

Which model runs is therefore entirely determined by which env file `pydantic-settings` happens to resolve (`env_file=(".env", "../.env")`), and by the process working directory.

---

## 5. Exact Blocking Issue

There is no single blocker. There are five, and they are ranked below by how much they contribute to the reported symptom. Each is explicitly classified as `APPLICATION BUG` or `ENVIRONMENT / CREDENTIAL ISSUE`.

### BLOCKER 1 — Retrieval is hard-coupled to a second, unverifiable credential+model pair, with no fallback and a silent default

**Classification: APPLICATION BUG** (with an embedded `ENVIRONMENT / CREDENTIAL ISSUE`)

The chat provider and the embedding provider are configured independently and there is no code path that makes them agree.

- `EMBEDDING_PROVIDER=google` (`.env`), `GEMINI_EMBEDDING_MODEL=gemini-embedding-2`, `GEMINI_EMBEDDING_DIMENSION=768`.
- `AGENT_DEFAULT_PROVIDER=groq` (`.env`).
- `backend/app/services/embedding/factory.py :: get_embedding_provider()` lines 15-17: `"google"` → Gemini, `"openai"` → OpenAI, **and every other value silently falls through to Gemini**. Setting `EMBEDDING_PROVIDER=groq`, `EMBEDDING_PROVIDER=none`, or a typo does not raise — it returns a Gemini provider that then requires `GEMINI_API_KEY`.
- **There is no mock, deterministic, offline, or local embedding provider anywhere in the repository.** Embeddings are an unconditional outbound-network dependency of every repository question.

The failure cascade, exactly:

1. `RepositorySearchTool.aexecute` → `HybridSearchEngine.search` → `_execute_search`.
2. `_execute_search` calls `get_embedding_provider()` then `await embed_provider.embed_query(query)`.
3. `GeminiEmbeddingProvider._embed_batch_with_retry` POSTs to `{BASE_URL}/models/gemini-embedding-2:batchEmbedContents?key=…`. It retries on `(429, 500, 502, 503, 504)` with up to `max_retries=4`. **A 404 — the response an invalid model identifier produces — is not in the retry set.** It falls into the `else` branch and raises `ForgeAIException(status_code=502, message=f"Gemini embedding API error (404): {safe_msg}")`.
4. That exception propagates out of the tool. `tools_node` (`graph.py:164`) catches it and appends the error as `ToolMessage` content (`graph.py:233`).
5. The model receives "your search failed" as a tool result, has 4 remaining iterations, and — despite the "Strict Grounding & No Hallucination" clause in `DEFAULT_AGENT_SYSTEM_PROMPT` — produces a fluent answer from parametric knowledge.
6. The user receives a confident, well-formatted, **ungrounded** answer over SSE. Nothing in the response distinguishes it from a grounded one. HTTP 200.

This is the mechanism behind "the application cannot currently be reliably exercised with a real model API." It is not that the model cannot be called — it is that the *retrieval* half of RAG fails independently of the model, fails silently, and the failure is laundered into a plausible answer.

The `gemini-embedding-2` identifier itself is **UNVERIFIED**: this audit could not reach `ai.google.dev` (egress blocked) and cannot assert whether it is valid, renamed, or retired. That portion is an `ENVIRONMENT / CREDENTIAL ISSUE`. The absence of any fallback, the silent factory default, and the non-retried 404 mapping to an opaque 502 are all `APPLICATION BUG`.

A secondary and equally fatal precondition: `_execute_search` resolves ACTIVE `RepositoryIndexVersion` rows first and **returns `[]` if none exist**. An un-indexed repository therefore returns zero results with no error at all — silently ungrounded, no embedding call even attempted. And indexing itself requires the same Gemini embedding call to succeed (`IngestionEngine.run_indexing` → `embed_documents`, validated at `engine.py:434` with `"Index validation failed"`), so a broken embedding model means the repository can never be indexed in the first place.

### BLOCKER 2 — `MockChatModelProvider` is a production-selectable code path, and the shipped template selects it

**Classification: APPLICATION BUG**

`MockChatModelProvider` lives at `backend/app/agent/models.py:140`, inside the production provider module, registered in the production factory `get_chat_model_provider` (@784), selected by one environment variable. `.env.example:59` ships `AGENT_DEFAULT_PROVIDER=mock`.

Its `ainvoke` (@165-258) is not a passive stub. It actively simulates plausible agent behaviour:

- returns `response_override` if supplied;
- else returns `default_response` if it differs from `"Mock agent reasoning completed."`;
- else, on the first turn with no `ToolMessage` present and a query containing `"plan"`, `"add"`, or `"fix"`, **fabricates a `search_repository` tool call** — so the tool loop, the SSE `agent.tool_call`/`agent.tool_result` events, and the frontend all light up exactly as they would with a real model;
- else fabricates a complete JSON `ImplementationPlan` hardcoding `"file_path": "app/api/v1/agent.py"` and `"test_strategy": "pytest tests/integration/test_phase5c_patch_and_test_api.py -v"`;
- else returns `f"Forge AI repository investigation complete for query: '{user_text}'. All codebase references verified."`

That last string asserts verification that never occurred. There is no banner, header, log warning, response field, or UI indicator anywhere that reveals mock mode is active. A demo run in mock mode is visually indistinguishable from a real one.

### BLOCKER 3 — The multi-agent engineering runtime is not connected to any model or to HTTP

**Classification: APPLICATION BUG**

- `backend/app/agent/multi_agent/coder.py` — `CoderAgent` accepts `model_provider` at @34 and **never calls it**. There is no `ainvoke` in the file. On `PatchService` failure it logs `"PatchService direct synthesis fallback: %s"` and fabricates `"--- a/{target_file}\n+++ b/{target_file}\n@@ -1,3 +1,6 @@\n+# Verified implementation\n"` with `target_file` defaulting to `app/api/v1/agent.py`.
- `backend/app/agent/multi_agent/tester.py` — `TesterAgent` **never calls a model either**. Its fallback sets `test_passed = True` and emits `status: "PASSED"`, `exit_code: 0`, `stdout: "====================== 1 passed in 0.42s ======================"`, `duration_ms: 420`. A green test result is manufactured, not observed.
- `backend/app/agent/multi_agent/orchestrator.py` — `EngineeringOrchestrator` requires four providers, builds a real supervisor `StateGraph`, and implements 5 approval gates in `_route_next_step` (@110). It is **never constructed anywhere in `app/`**. It is only re-exported from `multi_agent/__init__.py` and mentioned in a docstring.
- `backend/app/api/v1/agent.py` `POST /tasks` (~@578) documents itself as "Initializes a multi-agent engineering task managed by the EngineeringOrchestrator" but its body inserts `AgentSession` + `AgentTask(active_agent="SUPERVISOR")`, commits, and returns. No orchestrator, no graph, no model call.
- `backend/app/agent/multi_agent/config.py` `RoleProviderConfig` reads `os.getenv(...)` **at import time**, which bypasses `pydantic-settings` `.env` loading entirely (`.env` values are loaded into the `Settings` object, **not** into `os.environ`). Its per-role defaults (`gemini` / `openai` / `groq` / `gemini-2.5-pro`) would silently disagree with `.env` even if it were consumed. It is dead code. So is `AgentConfig` in `agent/config.py`.

So half the advertised multi-agent capability has no model behind it, and none of it is reachable over HTTP.

### BLOCKER 4 — Tool declarations are hardcoded, incomplete, and always sent

**Classification: APPLICATION BUG**

`_get_gemini_tools_declaration` (`models.py:279`) and `_get_openai_tools_declaration` (`models.py:552`) are hand-written JSON literals declaring exactly three tools: `search_repository`, `search_symbol`, `get_file`. The registry `get_agent_tools()` returns **eleven** (adding `ProposePatch`, `RunTests`, `ApplyPatch`, `CreateBranch`, `GitStatus`, `CommitChanges`, `PushBranch`, `CreatePullRequest`). **The declarations are not derived from the registry.** Eight tools are invisible to the model, which cannot call what it has not been told about — this is why the write-path agent capabilities can only be reached through frontend fabrication.

Worse, `OpenAIChatModelProvider.ainvoke` (@672) builds its payload with `"tools": self._get_openai_tools_declaration()` **unconditionally**, on every call. This includes calls whose prompts demand strict JSON output and no tool use — `ReviewerAgent` and `PlannerAgent`. A model offered tools will sometimes emit a tool call instead of prose; the parser then reads `choices[0].message.content` as empty and returns `AIMessage(content="")`. Which leads directly to:

### BLOCKER 5 — Every model failure mode degrades into a fabricated success

**Classification: APPLICATION BUG**

- `backend/app/agent/multi_agent/reviewer.py` — `review_status` is pre-initialised to `"APPROVED"` and `summary` to `"Review completed. No blocking security or regression findings detected."`, then the parse is wrapped in `except Exception as err: logger.info("Using default clean review output due to model response format: %s", err)`. **Any** failure — empty content from a tool call, a fence variant, a truncated response from `AGENT_MAX_TOKENS=4096`, a timeout, malformed JSON — produces a clean APPROVED review with zero findings, logged at INFO. A security reviewer that returns "approved" when it fails is worse than no reviewer.
- `backend/app/agent/multi_agent/planner.py` (@116-125) — parse failure synthesises `ImplementationPlan(summary=f"Plan: {state['title']}", approach="Investigate affected routers and verify with targeted unit test suite.", affected_files=[], test_strategy="pytest -v", risks=[...])`.
- `backend/app/services/github/pr_review_service.py` — GitHub diff fetch failure logs at INFO and substitutes a hardcoded synthetic diff (`"+    # Refactored token calculation"`), then reviews *that*. The SHA drift guard is wrapped in `except Exception as e: logger.debug("Skipping live SHA check in offline/test mode: %s", e)`.
- The frontend then fabricates the patch, workspace, test run, commit SHA, and PR URL regardless of what the backend returned, because `AgentMessage.tsx:135` passes the literal `"mock-approval-123"` where a UUID is required and `isUUID()` therefore fails **open** into the fabricating branch.

### Configuration defects that compound all five

- `get_chat_model_provider` (@784) **never passes `timeout_seconds`** to any provider constructor, so `AGENT_TIMEOUT_SECONDS=60.0` never reaches a provider; each silently uses its own `timeout_seconds=60.0` default. The setting is inert.
- `AgentService.stream_chat` computes a timeout at @349 and **never applies it** to `graph.astream`, making the `except TimeoutError` branch at @411 unreachable from the graph. Only the non-streaming `execute_chat` (@204) actually wraps in `asyncio.wait_for`. The production path is the streaming one.
- `GITHUB_WEBHOOK_SECRET` is **absent from `.env`**, so HMAC verification runs against the insecure in-code default `"test-github-webhook-secret-change-in-production"` (`config.py:89`). `JWT_SECRET` and `ENCRYPTION_KEY` have similarly insecure in-code defaults, though both are set in `.env`.
- The webhook dispatches with `background_tasks.add_task(_run_pr_review_background, str(review_task.id))` (`github_webhooks.py:106-107`) — a `str` into a `uuid.UUID`-annotated parameter — and the whole dispatch is gated behind `if settings.ENVIRONMENT != "test"`, so no test ever executes it.
- `backend/app/workers/main.py:25` registers only `health_check_job` and `index_repository_task`. **No AI or review task is registered with ARQ.** PR review executes inside the web process via FastAPI `BackgroundTasks`, so it dies with the request worker and has no retry, no visibility, and no queue backpressure.

---

## 6. RAG / Embedding Status

**Are the embeddings real?** Yes — the only embedding implementation that exists is real. `GeminiEmbeddingProvider` (`backend/app/services/embedding/gemini.py`) POSTs genuine `batchEmbedContents` requests with per-text payloads `{"model": f"models/{self._model}", "content": {"parts": [{"text": t}]}, "taskType": task_type, "outputDimensionality": self._dimension}`. There are no deterministic fake embeddings, no hash-based vectors, and no cached embedding shortcut in the production path.

**But:** the only place 768-dimension vectors are ever *written* in a test is `conftest.py`'s `indexed_tool_repo` fixture (@197-198), which seeds hand-written **one-hot** vectors. And `embed_query` returns `[0.0] * dimension` — a zero vector — for empty input text, which would make every cosine distance identical rather than raising.

Step-by-step reality of the pipeline:

| Step | Implementation | File | Symbol | Real/Mock | Persistence |
| --- | --- | --- | --- | --- | --- |
| Repository acquisition | Real clone/bind | `backend/app/services/ingestion/engine.py` | `IngestionEngine.run_indexing` (@81) | REAL | PostgreSQL `Repository`, `RepositoryBranch` |
| File parsing | Real | `backend/app/services/ingestion/engine.py` | `CodeChunker.parse_and_chunk_file` (@251) | REAL | `RepositoryFile` |
| AST extraction / chunking | Real tree-sitter (py/ts/js/md/json/yaml) | `backend/app/services/ingestion/chunker.py` | `CodeChunker` | REAL | `CodeChunk` |
| Embedding text assembly | `f"{chunk.context_header}\n{chunk.content}"` | `engine.py` @294 | — | REAL | — |
| Embedding generation | Real HTTP to Gemini | `backend/app/services/embedding/gemini.py` | `embed_documents`, `_embed_batch_with_retry` | **REAL — hard network dependency, no fallback** | — |
| Vector storage | `Vector(768)` + HNSW `vector_cosine_ops` | `backend/alembic/versions/0004_repo_intelligence.py` @175, @200-201 | `ChunkEmbedding` | REAL | **Persistent** PostgreSQL/pgvector |
| Index validation | chunk-count vs embedding-count | `engine.py` @434 | `"Index validation failed"` | REAL | — |
| Query embedding | Real HTTP to Gemini | `gemini.py` | `embed_query` | REAL (returns zero-vector for empty text) | — |
| Dense search | `cosine_distance(query_vector)` limit 60 | `hybrid.py` `_execute_search` | pgvector operator | **REAL — never exercised by any test** | — |
| Dense search (SQLite) | loads all rows, pure-Python cosine | `hybrid.py` @356 | `python_cosine_distance` | REAL algorithm, **no index, O(n)** | — |
| Sparse search | `ts_rank_cd(search_vector, plainto_tsquery('english', q))` | `hybrid.py` | — | REAL, silently degrades via `try/except` | Persistent tsvector, weights at migration @149-151 |
| Symbol search | Real | `hybrid.py` | `extract_query_code_terms` (@311) | REAL | — |
| Fusion | RRF, k=60 | `hybrid.py` | — | REAL | — |
| Chunk → prompt | `truncate_tool_output(chunk.content, max_chars=4000)` → `ToolMessage(json.dumps(...))` | `repository_search.py` @115, `graph.py` @233 | — | **REAL — confirmed** | — |

**Does retrieved context actually reach the model?** **Yes — confirmed, and this is important.** `RepositorySearchTool.aexecute` returns real chunk *content* (not just IDs or metadata) under `data={"query", "total_results", "results"}`, truncated to 4000 characters per chunk. `tools_node` serialises the entire tool result with `json.dumps(res.model_dump())` into a `ToolMessage` (`graph.py:233`) which is appended to the message list and sent to the model on the next iteration. The grounding wiring is genuine. The problem is not the wiring; it is that the wiring can carry an error string instead of code and nothing downstream notices.

**Unified vector space.** The schema hardcodes 768 dimensions (`Vector(768)` in both the migration and `backend/app/models/codebase.py:235`), with `ChunkEmbedding` defaults `provider="google"`, `model="gemini-embedding-2"`, `dimension=768`, and a unique constraint `uq_chunk_embed_version` on `(chunk_id, provider, model, embedding_version)`. This is well-designed for versioned re-embedding, but it also means the alternative provider (`text-embedding-3-small`, native 1536) cannot be dropped in without explicit dimension reduction. Switching embedding providers is a migration, not a config change.

---

## 7. Phase 7B Real AI Status

Phase 7B is the **most real** part of the AI runtime and simultaneously the one with the most convincing fabrication fallbacks.

**Genuinely real, verified by code inspection:**

1. HMAC-SHA256 webhook signature verification — `backend/app/services/github/webhook_verifier.py`, called at `github_webhooks.py:63`. Real constant-time comparison, real payload-size validation.
2. Delivery-ID deduplication / replay protection — `github_webhooks.py:82`.
3. Immutable `PullRequestSnapshot` creation — `backend/app/services/github/pr_ingestion_service.py`.
4. Scoped diff parsing and AST symbol context expansion — `backend/app/services/github/diff_context_service.py`.
5. Adversarial prompt-injection defence — `backend/app/services/github/sanitizer.py` :: `sanitize_pr_text`, `wrap_untrusted_content`.
6. **The ReviewerAgent model call itself** — `backend/app/agent/multi_agent/reviewer.py:78`, `response = await self.model_provider.ainvoke(messages)`, with a real system prompt (@25) demanding structured JSON findings. This is a genuine model invocation against whatever `get_chat_model_provider()` resolves (currently Groq).
7. Findings persistence — real `ReviewFinding` rows plus `PullRequestReviewTask` counters (`total_findings_count`, `critical_count`, `agent_review_id`, `lifecycle_state`).
8. Read-only guarantee — **holds**. No GitHub mutation (no PR comment, no review submission, no status check) occurs on the review path.

**Where real AI execution stops and mock behaviour begins — three exact lines:**

1. **`PRReviewService.execute_review`, GitHub diff fetch.** On any exception it logs `"Could not fetch remote PR diff from GitHub (%s). Proceeding with synthetic fallback."` at INFO and sets

   ```
   diff_text = (f"--- a/{repo_name}/core.py\n+++ b/{repo_name}/core.py\n@@ -1,4 +1,6 @@\n"
                f" def main():\n-    return 0\n+    # Refactored token calculation\n+    return 1\n")
   ```

   The model then reviews a two-line invented diff. The review completes, findings persist, the lifecycle reaches `REVIEW_READY`, and the UI shows a finished review of code that does not exist in the pull request. **This is the boundary line.** A missing GitHub installation token, an expired JWT, a 404 on a private repo, a network blip — all produce a completed, plausible, wrong review.

2. **`ReviewerAgent.execute`, response parsing.** `except Exception as err: logger.info("Using default clean review output due to model response format: %s", err)` over pre-initialised `review_status = "APPROVED"` / `summary = "Review completed. No blocking security or regression findings detected."`. Any parse failure produces a clean approval with zero findings. Given Blocker 4 (tools are always sent, even on this JSON-only prompt), an empty-content response is a realistic and untracked outcome.

3. **SHA drift check.** Wrapped in `except Exception as e: logger.debug("Skipping live SHA check in offline/test mode: %s", e)`. The protection the baseline reports as "SHA drift check PASS" is silently skippable at DEBUG level whenever GitHub is unreachable.

**On the "Phase 7B real-world E2E audit: 6/6 checks + SHA drift PASS" baseline.** The script producing that result is `scratch/audit_phase7b_real_world.py` (297 lines, untracked). Two findings materially qualify what it proves:

- Line 78-79: `engine = create_async_engine("sqlite+aiosqlite:///:memory:")`. It runs against **in-memory SQLite, not PostgreSQL** — so no pgvector, no HNSW index, no `ts_rank_cd`, and the pure-Python cosine branch.
- Line 256: `mock_model = MockChatModelProvider(default_response=json.dumps(mock_reviewer_response))`, then `await review_service.execute_review(task1.id, model_provider=mock_model)`. The `mock_reviewer_response` dict (@240-255) hand-authors the exact review — `"status": "CHANGES_REQUESTED"`, one `CRITICAL`/`SECURITY` finding in `app/core/rate_limiter.py` lines 12-15 — and the assertions immediately after (@261-264) verify `total_findings_count == 1` and `critical_count == 1`. **The audit asserts the values it just injected.** It is a circular check of the persistence and lifecycle plumbing, which it validates correctly, and it proves nothing whatsoever about real model behaviour.

So: Phase 7B's *plumbing* is real and well-tested. Phase 7B's *intelligence* has never been executed against a real model in any recorded run.

---

## 8. Streaming Status

**Classification: C (Buffered response) at the transport layer, D (Unsupported) at the model layer.**

There is no real model streaming anywhere in Forge AI, and there is no simulated token streaming either. What exists is a real SSE transport carrying coarse lifecycle events, with the complete answer delivered in a single terminal frame.

Evidence, layer by layer:

| Layer | File | Symbol | Finding |
| --- | --- | --- | --- |
| Provider ABC | `backend/app/agent/models.py` | `BaseChatModelProvider` (@120) | Declares abstract `async def ainvoke` (@135) and **nothing else. There is no `astream` method on the base class or on any subclass.** |
| Gemini provider | `backend/app/agent/models.py` | `GeminiChatModelProvider.ainvoke` (@418) | Calls `:generateContent`, not `:streamGenerateContent`. Single response, parsed whole. |
| OpenAI/Groq provider | `backend/app/agent/models.py` | `OpenAIChatModelProvider.ainvoke` (@672) | Payload contains `model`, `messages`, `temperature`, `tools`, optional `max_tokens`. **`"stream": true` is never set.** No SSE parsing of the upstream response. |
| Graph | `backend/app/agent/graph.py` | `agent_node` (@90) | `await provider.ainvoke(messages)` — awaits a complete message. |
| Service | `backend/app/services/agent_service.py` | `stream_chat` (@287), `graph.astream(..., stream_mode="updates")` (@357) | `stream_mode="updates"` emits one event per **completed graph node**, not per token. This is LangGraph node-level streaming, not model-level. |
| SSE framing | `backend/app/services/agent_service.py` | `_format_sse` (@295-296) | `f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"` — correct SSE. Real transport. |
| Terminal frame | `backend/app/services/agent_service.py` | @436-446 | `agent.completed` carries the **entire** `answer` string in one payload. |
| Frontend parser | `frontend/src/lib/agent-api.ts` | `parseSSEStream` (@70-147) | Correct incremental SSE frame parsing via `ReadableStream.getReader()`. Dispatches with `event: currentEvent as any` (@107-110) — no type narrowing. |
| Frontend event union | `frontend/src/types/agent.ts` | `AgentStreamEventType` (@237-275) | **38 members. Zero token/delta/chunk members.** There is no event type that *could* carry a partial token. 14 declared events have no `case` in the hook, including `agent.pr.created`. |
| Frontend rendering | `frontend/src/hooks/useAgentChat.ts` | `case "agent.completed"` (@185-201) | `content: data.answer \|\| "Answer generated."` (@194) is the **only** assignment to `msg.content` in the entire streaming path. There is no `content: msg.content + delta` anywhere in the codebase. |

The user experience is therefore: a spinner, then intermediate `agent.tool_call` / `agent.tool_result` activity indicators (which do give a genuine sense of progress), then the whole answer appearing at once. Perceived latency equals full end-to-end model latency plus up to 5 tool iterations. With `AGENT_MAX_TOKENS=4096` on a reasoning-capable model, that is a long silent wait.

Two aggravating details. `AbortController` exists at `useAgentChat.ts:115` but there is **no timeout or watchdog** — a hung upstream connection leaves the UI spinning indefinitely, because (per Section 5) `AGENT_TIMEOUT_SECONDS` is applied neither to the provider nor to `graph.astream`. And `cancelStream` (@20-34) marks aborted messages `"completed"`, so a cancelled request is recorded in the transcript as a successful one.

`sendAgentMessage` (`agent-api.ts`, POST `/chat` with `stream: false` @163,166) — the non-streaming path that *does* correctly apply `asyncio.wait_for` on the backend — is **never invoked** by the production frontend.

---

## 9. Test Reality

### What the suites actually contain

The backend suite is 39 collected test files (18 unit + 21 integration) containing **249 test functions**, with 5 `parametrize` decorators expanding to 38 cases — a static count of **282 collected items**. The reported baseline is 281. This one-item discrepancy could not be resolved because the audit sandbox has no installed Python dependencies and the project virtualenv is a Windows cp312 environment that cannot be executed from Linux. It is almost certainly a `parametrize` counting nuance rather than a defect, and is noted only for completeness.

`backend/tests/conftest.py` sets exactly five environment variables at @9-14 — `ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ENCRYPTION_KEY` — uses `sqlite+aiosqlite` (@11, @25-31), and monkey-assigns `app.core.database.AsyncSessionLocal` (@42). Notably it contains **no autouse AI fixture and no neutralisation of AI credentials**. There is no `skipif`, `skip`, `xfail`, or `importorskip` anywhere in the suite, and no registered custom markers (only `asyncio` and `parametrize`).

### What the 281 backend tests prove

| Category | Proven? | Evidence |
| --- | --- | --- |
| **A. Architecture** | **YES, strongly** | Routes, schemas, DI, ORM relationships, migrations, multi-tenant scoping, RBAC. This is the suite's real strength. |
| **B. Business logic** | **YES, strongly** | Approval gates, lifecycle state machines, dedup, snapshot immutability, sanitiser behaviour, patch/workspace services. |
| **C. Retrieval** | **PARTIALLY** | RRF fusion, `extract_query_code_terms`, `is_implementation_query`, and result shaping are tested — but always through the **SQLite branch** with `python_cosine_distance` over hand-written one-hot vectors from `conftest.py:197-198`. |
| **D. Agent behaviour** | **PARTIALLY** | Graph wiring, `tool_router` termination, iteration cap, and tool dispatch are tested by injecting `MockChatModelProvider` through `config["configurable"]["model_provider"]`. Real model reasoning is not tested. |
| **E. Real LLM execution** | **NO** | **Zero tests make a real chat-model call.** No test asserts against a live provider. |
| **F. Real embeddings** | **NO (with one accidental exception)** | `tests/integration/test_retrieval_integration.py:131` makes a **real, unpatched Gemini `batchEmbedContents` call**. It is non-hermetic and network-dependent, not a deliberate real-embedding test. |
| **G. Real GitHub integration** | **NO (with one accidental exception)** | `tests/integration/test_github_pr_reviewer_api.py:241` makes **two real calls to `api.github.com`**, both swallowed — after which the service reviews its hardcoded synthetic diff. |
| **H. Real streaming** | **NO** | 3 tests exercise `astream`/SSE with a mock provider and assert against the **buffered response body**, not incremental frames. Token streaming is untestable because it does not exist. |

### Specific coverage gaps, stated precisely

- **pgvector `cosine_distance` is NOT-TESTED.** Every test takes the `is_sqlite` branch. The HNSW index, the `vector_cosine_ops` operator class, and the `Vector(768)` binding are exercised only by the migration running, never by a query.
- **`ts_rank_cd` sparse search is NOT-TESTED.** SQLite takes the Python substring-counting path. The tsvector weights configured at migration @149-151 are never validated against a real query.
- **Real embeddings are NOT-TESTED** as a deliberate assertion.
- **`ReviewerAgent` with a real model is NOT-TESTED.**
- **Webhook → background dispatch is NOT-TESTED** — `github_webhooks.py:106-107` is gated behind `if settings.ENVIRONMENT != "test"`, and `conftest.py` sets `ENVIRONMENT=test`. The `str` → `uuid.UUID` argument mismatch on that line is consequently invisible to CI.
- **The PR reviewer E2E test is circular.** It injects the review JSON it then asserts.
- **Zero Category-A real-LLM tests, zero Category-C in-test fake provider classes, zero Category-E HTTP-transport mocks** (no `respx`, no `httpx.MockTransport`). This last point is significant: because there is no transport-level mocking anywhere, the suite cannot test provider *error* handling — 401, 404, 429, 500, malformed JSON, empty `choices` — at all. Every provider failure branch in `models.py` and `gemini.py` is completely uncovered.

### The gap between TESTED and ACTUALLY EXECUTABLE WITH A REAL MODEL

Mocks are the right tool for deterministic CI, and this suite uses them competently. The problem is not the mocks. The problem is that **the mock is the same class the production factory can return**, injected through the same parameter the production graph reads, so passing tests and a fabricated demo are the same code path with a different environment variable. Nothing in the suite would fail if every real provider in `models.py` were deleted.

Concretely: the suite proves Forge AI is a correct, well-structured, multi-tenant, secure application that orchestrates AI. It does not prove — and cannot currently prove — that any AI ever ran.

The 44 frontend Vitest tests are subject to the same inversion, more severely: they assert against components whose fabricated branches (`MOCK_DIFF_CONTENT`, `getMockPatch`, the invented workspace/commit/PR values) are the *default* path, because the UUID guards fail open. Passing frontend tests actively certify the fabrication.

---

## 10. Environment Requirements

Reported as `CONFIGURED` / `MISSING` / `OPTIONAL` / `REQUIRED` / `UNKNOWN`. No secret values were read into context or printed.

### 1. Application startup

| Variable | Status | Requirement | Note |
| --- | --- | --- | --- |
| `ENVIRONMENT` | CONFIGURED (`development`) | REQUIRED | `test` value disables webhook background dispatch. |
| `DATABASE_URL` | CONFIGURED (`postgresql+asyncpg://…@localhost:5433/forgeai`) | REQUIRED | Port 5433 — non-default; must match `docker-compose.yml`. |
| `JWT_SECRET` | CONFIGURED | REQUIRED | Insecure in-code default exists (`config.py`). |
| `ENCRYPTION_KEY` | CONFIGURED | REQUIRED | Insecure in-code default exists. |

### 2. LLM

| Variable | Status | Requirement | Note |
| --- | --- | --- | --- |
| `AGENT_DEFAULT_PROVIDER` | CONFIGURED (`groq`) | REQUIRED | In-code default `google` (@120); `.env.example` default `mock`. Three conflicting values. |
| `GROQ_API_KEY` | **CONFIGURED** | REQUIRED (active provider) | — |
| `GROQ_BASE_URL` | CONFIGURED (`https://api.groq.com/openai/v1`) | REQUIRED | — |
| `GROQ_MODEL` | CONFIGURED (`openai/gpt-oss-120b`) | REQUIRED | — |
| `GEMINI_API_KEY` | **CONFIGURED** | REQUIRED (if provider `google`; **and always, for embeddings**) | — |
| `AGENT_GEMINI_MODEL` | CONFIGURED (`gemini-3.1-pro-preview`) | REQUIRED if provider `google` | Identifier **UNVERIFIED**. |
| `OPENAI_API_KEY` | **CONFIGURED** | OPTIONAL | — |
| `AGENT_OPENAI_MODEL` | CONFIGURED (`gpt-4o`) | OPTIONAL | — |
| `OPENAI_COMPATIBLE_BASE_URL` | **MISSING** (empty) | OPTIONAL | — |
| `OPENAI_COMPATIBLE_MODEL` | **MISSING** (empty) | OPTIONAL | — |
| `OPENAI_COMPATIBLE_API_KEY` | **MISSING** (present but empty) | OPTIONAL | — |
| `AGENT_TEMPERATURE` | CONFIGURED (`0.2`) | OPTIONAL | — |
| `AGENT_MAX_TOKENS` | CONFIGURED (`4096`) | OPTIONAL | Low for reasoning + JSON findings; truncation triggers the silent-APPROVED path. |
| `AGENT_TIMEOUT_SECONDS` | CONFIGURED (`60.0`) | OPTIONAL | **INERT** — never reaches any provider; never applied to `astream`. |

### 3. Embeddings

| Variable | Status | Requirement | Note |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | CONFIGURED (`google`) | REQUIRED | Unrecognised values silently resolve to Gemini. |
| `GEMINI_EMBEDDING_MODEL` | CONFIGURED (`gemini-embedding-2`) | REQUIRED | Identifier **UNVERIFIED**. Sole hard blocker candidate for RAG. |
| `GEMINI_EMBEDDING_DIMENSION` | CONFIGURED (`768`) | REQUIRED | Must equal the `Vector(768)` column. Changing it breaks the schema. |
| `OPENAI_EMBEDDING_MODEL` | CONFIGURED (`text-embedding-3-small`) | OPTIONAL | Native 1536-d — incompatible with `Vector(768)` without reduction. |

### 4. GitHub integration

| Variable | Status | Requirement | Note |
| --- | --- | --- | --- |
| `GITHUB_APP_ID` | CONFIGURED | REQUIRED | — |
| `GITHUB_CLIENT_ID` | CONFIGURED | REQUIRED | — |
| `GITHUB_CLIENT_SECRET` | CONFIGURED | REQUIRED | — |
| `GITHUB_PRIVATE_KEY` | CONFIGURED | REQUIRED | Correctly double-quoted 27-line PEM. |
| `GITHUB_PRIVATE_KEY_PATH` | CONFIGURED | OPTIONAL | Redundant with the inline key. |
| `GITHUB_WEBHOOK_SECRET` | **MISSING — absent from `.env`** | **REQUIRED** | Falls back to the insecure in-code default `"test-github-webhook-secret-change-in-production"` (`config.py:89`). Real GitHub deliveries will fail HMAC verification, which is exactly the condition that routes `PRReviewService` into its synthetic-diff fallback. |

### 5. Database

| Variable | Status | Requirement |
| --- | --- | --- |
| `DATABASE_URL` | CONFIGURED | REQUIRED — PostgreSQL 16 with the `vector` extension (`pgvector/pgvector:pg16`, `docker-compose.yml:5`). |

### 6. Redis / background workers

| Variable | Status | Requirement | Note |
| --- | --- | --- | --- |
| `REDIS_URL` | CONFIGURED (`redis://localhost:6379/0`) | REQUIRED | `redis:7-alpine` (`docker-compose.yml:25`); worker `python -m arq app.workers.main.WorkerSettings` (@83). |

**Frontend:** the only variable is `NEXT_PUBLIC_API_URL`. There is **no `frontend/.env*` file**, no `NEXT_PUBLIC_*` AI/model variable, and **no mock-mode flag** — so the frontend fabrication cannot be disabled by configuration at all.

**Minimum set for a genuine real-AI run of Demo A:** `ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ENCRYPTION_KEY`, `AGENT_DEFAULT_PROVIDER`, the matching provider key + base URL + model, **plus** `EMBEDDING_PROVIDER`, `GEMINI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_DIMENSION`, and `GEMINI_API_KEY` — the embedding credential is required *even when the chat provider is Groq or OpenAI*. That coupling is undocumented in `.env.example`.

### Dependency / SDK audit (Part 11)

Resolved versions from `backend/uv.lock`:

| Package | Resolved | Declared floor (`pyproject.toml`) | Concern |
| --- | --- | --- | --- |
| `langgraph` | **1.2.11** | `>=0.2.0` | **Major-version drift.** The floor was written against the 0.2 line; 1.x resolved. `StateGraph`, `START`, `astream(stream_mode=...)` remain valid in 1.x, so nothing is broken today, but the constraint provides no protection. |
| `langchain-core` | **1.6.0** | `>=0.3.0` | Same major-version drift. `AIMessage`, `ToolMessage`, `SystemMessage`, `HumanMessage` are stable. |
| `langgraph-checkpoint` | 4.2.0 | (transitive) | Present but **not wired**. No checkpointer configured — this is the natural home for real conversational memory. |
| `langsmith` | 0.11.1 | (transitive) | Present. No tracing configured. Would be the cheapest way to obtain real-call observability. |
| `httpx` | 0.28.1 | `>=0.27.0` | Fine. All provider I/O goes through this. |
| `pgvector` | 0.5.0 | `>=0.3.0` | Fine. `Vector(768)` and `.cosine_distance()` valid. |
| `sqlalchemy` | 2.0.52 | `>=2.0.30` | Fine. |
| `asyncpg` | 0.31.0 | `>=0.29.0` | Fine. |
| `pydantic` / `pydantic-settings` | 2.13.4 / 2.15.0 | `>=2.7.0` / `>=2.2.0` | Fine. |
| `fastapi` / `uvicorn` | 0.141.1 / 0.52.4 | `>=0.111.0` / `>=0.30.0` | Fine. |
| `arq` / `redis` | 0.28.0 / 5.3.1 | `>=0.25.0` / `>=5.0.4` | Fine. No AI task registered. |
| `tree-sitter` | 0.26.0 | `>=0.23.0` | Fine. |
| `pytest` / `pytest-asyncio` | 9.1.1 / 1.4.0 | `>=8.1.0` / `>=0.23.6` | `pytest-asyncio` 1.x is a major jump from the 0.23 floor; `asyncio_mode = "auto"` is configured and still supported. |
| **`openai`** | **ABSENT** | — | No vendor SDK. |
| **`google-genai` / `google-generativeai`** | **ABSENT** | — | No vendor SDK. |
| **`anthropic`** | **ABSENT** | — | No vendor SDK. |
| **`numpy`** | **ABSENT** | — | Why `python_cosine_distance` is hand-written pure Python. |
| **`tiktoken`** | **ABSENT** | — | No token counting anywhere; `AGENT_MAX_TOKENS=4096` is unenforced client-side and context overflow is undetectable before the call. |
| **`respx` / HTTP mocking** | **ABSENT** | — | Root cause of zero provider-error-path coverage. |

The all-`httpx`, zero-SDK design is a deliberate and defensible choice — it eliminates SDK churn and gives full control over retry and secret sanitisation. Its cost is that every provider quirk (streaming formats, tool-call schema variations, error envelopes) must be hand-maintained, and there is no vendor test double available. Frontend stack: Next.js 15.1 / React 19 / Vitest 1.6 — current and coherent.

---

## 11. Risks

1. **Silent ungrounded answers (SEVERITY: CRITICAL).** Embedding failure, missing index, or zero search results all produce a confident answer with no grounding indicator. For a code-intelligence product this is the single most damaging possible failure mode: the product's entire value claim is "grounded in your repository," and it cannot currently prove it delivered on that claim for any given response.
2. **Silent security approvals (SEVERITY: CRITICAL).** `ReviewerAgent` returns `APPROVED` with zero findings on any parse failure, logged at INFO. A reviewer that fails to "no problems found" will eventually approve a real vulnerability.
3. **Reviewing a fabricated diff (SEVERITY: CRITICAL).** With `GITHUB_WEBHOOK_SECRET` absent and GitHub fetch failures logged at INFO, the most likely real-world outcome is a completed review of `pr_review_service.py`'s hardcoded two-line synthetic diff, presented in the UI as a genuine review.
4. **Frontend fabrication is unconditional and uncontrollable (SEVERITY: CRITICAL).** No flag, no env var, no build mode disables it. `AgentMessage.tsx:135` guarantees the guards fail open. Any demo will show a fabricated patch, workspace, test pass, commit SHA, and PR URL — and the 44 passing Vitest tests certify that behaviour as correct.
5. **`.env.example` ships `AGENT_DEFAULT_PROVIDER=mock` (SEVERITY: HIGH).** Every new developer, every fresh CI environment, and every container built from the template runs a fabricating model that announces `"All codebase references verified."`
6. **Split provider configuration (SEVERITY: HIGH).** Chat and embedding providers are configured independently with no validation that both are satisfiable. Three conflicting `AGENT_DEFAULT_PROVIDER` values exist across `config.py`, `.env.example`, and `.env`.
7. **Unverifiable model identifiers (SEVERITY: HIGH).** `gemini-3.1-pro-preview` and `gemini-embedding-2` could not be validated. Nothing in the codebase validates a model name at startup, so an invalid identifier surfaces as a runtime 404 → opaque 502, deep inside a tool call, at the worst possible moment.
8. **No timeout anywhere on the production path (SEVERITY: HIGH).** `AGENT_TIMEOUT_SECONDS` reaches neither provider nor stream; the frontend has no watchdog. A hung upstream hangs the UI indefinitely, and `cancelStream` records the abandoned request as `"completed"`.
9. **8 of 11 tools invisible to the model (SEVERITY: HIGH).** Hardcoded 3-tool declarations mean the entire write path (patch, test, branch, commit, push, PR) is unreachable by model decision — which is precisely the gap the frontend fabrication was built to paper over.
10. **`tools` sent on JSON-only prompts (SEVERITY: MEDIUM-HIGH).** Directly induces the empty-content responses that trigger risks 2 and the planner fallback.
11. **PR review runs in the web process (SEVERITY: MEDIUM-HIGH).** FastAPI `BackgroundTasks` rather than ARQ: no retry, no durability, no backpressure, dies with the worker. `workers/main.py:25` registers no AI task. A restart silently loses in-flight reviews.
12. **Insecure secret defaults (SEVERITY: MEDIUM-HIGH).** `GITHUB_WEBHOOK_SECRET`, `JWT_SECRET`, `ENCRYPTION_KEY` all have working insecure in-code defaults, so a misconfigured deployment starts successfully rather than refusing to boot.
13. **API key in a URL query string (SEVERITY: MEDIUM).** `gemini.py` builds `…:batchEmbedContents?key={self._api_key}`. Any exception, access log, or proxy log that captures the URL leaks the credential. `sanitize_secret_text` protects response bodies, not request URLs.
14. **Embedding dimension is structurally locked (SEVERITY: MEDIUM).** `Vector(768)` in schema and migration; the alternative provider is natively 1536-d. Provider migration requires a schema migration and full re-embedding.
15. **`stream_mode="updates"` cannot ever carry tokens (SEVERITY: MEDIUM).** Real streaming needs provider `astream`, a `messages`/custom stream mode, new event types in the 38-member union, and an accumulating reducer in `useAgentChat`. It is a four-layer change, not a flag.
16. **No AI observability (SEVERITY: MEDIUM).** No token accounting, no cost tracking, no latency metrics, no request/response persistence for model calls. `langsmith` is installed but unconfigured. There is currently no way to answer "did a real model actually run, and what did it cost?" after the fact.
17. **Non-hermetic tests (SEVERITY: MEDIUM).** `test_retrieval_integration.py:131` and `test_github_pr_reviewer_api.py:241` make real network calls. CI is network-dependent and will flake or silently change meaning offline.
18. **Zero provider-error-path coverage (SEVERITY: MEDIUM).** No HTTP transport mocking exists, so no test covers 401/404/429/500/malformed-JSON/empty-`choices` handling — the exact branches that matter most for real-model reliability.
19. **Dead architecture drift (SEVERITY: LOW-MEDIUM).** `EngineeringOrchestrator`, `role_provider_config`, `AgentConfig`, and `sendAgentMessage` are all unreachable. `POST /agent/tasks` documents behaviour it does not perform. 14 declared SSE events have no handler.
20. **`MAX_AGENT_ITERATIONS = 5` (SEVERITY: LOW-MEDIUM).** For a genuinely agentic repository investigation (search → read → search again → read again → synthesise), five iterations is tight; the cap terminates silently with no signal to the user that reasoning was truncated.

---

## 12. Recommended Phase 7C Implementation Plan

**NOT IMPLEMENTED. This is a recommended sequence only, provided for review.**

**1. Resolve the provider/model identity question first — before any code changes.**
Run the two probes in Appendix B against `${GROQ_BASE_URL}/chat/completions` and `…/models/${GEMINI_EMBEDDING_MODEL}:batchEmbedContents`. Record actual HTTP status codes. Everything below branches on those two results, and no amount of refactoring helps if the model identifiers are wrong. Deliverable: a one-page status record naming the exact working chat model and embedding model.

**2. Centralise model/provider configuration into a single validated resolver.**
One function that resolves chat provider, chat model, embedding provider, embedding model, dimension, timeout, and max-tokens together; validates them as a coherent set; refuses to start (or logs a loud structured WARNING) on inconsistency; and threads `AGENT_TIMEOUT_SECONDS` through to every provider constructor. Delete or relocate the three-way `AGENT_DEFAULT_PROVIDER` conflict so exactly one source of truth exists. Retire `role_provider_config`'s import-time `os.getenv` reads.

**3. Make real LLM execution provable and mock mode impossible to enter by accident.**
Move `MockChatModelProvider` out of the production module into `tests/`, or gate it behind an explicit `ALLOW_MOCK_MODEL=true` that logs a startup WARNING and stamps every response with a `provider`/`model`/`mock` marker. Change `.env.example:59` away from `mock`. Add `provider`, `model`, and `grounded` fields to the SSE `agent.completed` payload and surface them in the UI, so "did a real model run and was it grounded?" is answerable by looking at the screen. Also stop sending `tools` on prompts that demand JSON output.

**4. Make embeddings survivable.**
Add an offline/deterministic embedding provider for development and CI, make `get_embedding_provider()` raise on unrecognised values instead of silently defaulting to Gemini, add 404 to a distinct non-retryable-but-clearly-reported class, move the API key from the URL query string to a header, and add a startup embedding health check that fails fast and loudly rather than at query time.

**5. Verify real retrieval against real PostgreSQL.**
Add a PostgreSQL+pgvector test path (testcontainers or a compose-backed CI service) so `cosine_distance`, the HNSW index, and `ts_rank_cd` are exercised at least once. Index one real repository end-to-end with real embeddings and assert that a known query returns known chunks. Remove the silent `try/except` around full-text search, or make its degradation observable.

**6. Make ReviewerAgent fail loudly.**
Remove the pre-initialised `APPROVED` default. A parse failure must produce an explicit `REVIEW_FAILED` lifecycle state, not a clean approval. Remove the synthetic-diff fallback in `PRReviewService` — a diff that cannot be fetched must fail the task. Make the SHA drift check's exception path explicit rather than `logger.debug`. Set `GITHUB_WEBHOOK_SECRET` in the environment and remove the insecure in-code default.

**7. Implement real streaming as a coherent four-layer change.**
Add `astream` to `BaseChatModelProvider` and both real providers (`:streamGenerateContent` for Gemini, `"stream": true` + SSE delta parsing for OpenAI/Groq); switch `stream_chat` to a token-carrying stream mode; add `agent.token` (or equivalent) to `AgentStreamEventType`; add an accumulating `content: msg.content + delta` reducer in `useAgentChat`. Keep `agent.completed` as the authoritative final value so existing tests and clients continue to work.

**8. Make provider failure graceful and visible.**
A dedicated exception handler mapping provider failures to meaningful HTTP statuses (401 → configuration error, 404 → invalid model, 429 → rate limited, 5xx → upstream unavailable) with distinct SSE `agent.error` payloads the frontend renders as errors rather than answers. Apply a real timeout to `graph.astream`. Add a frontend watchdog. Stop marking cancelled streams `"completed"`. Add HTTP transport mocking so every one of these branches gets a test.

**9. Optional local-model fallback (e.g. Ollama).**
Only after items 1–8. The `openai_compatible` provider already exists and is unconfigured — a local OpenAI-compatible endpoint needs only `OPENAI_COMPATIBLE_BASE_URL` and `OPENAI_COMPATIBLE_MODEL`, no new code. Note that this solves the *chat* dependency only; embeddings would need a separate local implementation, and any local embedding model must produce 768 dimensions or the schema must change. **Not installed as part of this audit, per instruction.**

**10. End-to-end real-world acceptance test.**
A single opt-in, network-flagged acceptance run (excluded from the default suite so the 281/44 baselines stay hermetic and green) that indexes a real repository with real embeddings, asks a real question through a real model, asserts the answer cites retrieved chunks, and drives a real PR review to model-generated findings with zero GitHub mutations. This is the artifact that would let Forge AI claim a real AI runtime.

Sequencing note: items 1–4 are the critical path and unblock the reported symptom. Items 5–6 convert correctness into confidence. Items 7–8 are user-facing quality. Items 9–10 are hardening. The frontend fabrication removal (`AgentPlanView.tsx`, `AgentDiffView.tsx`, `AgentGitPanel.tsx`, `AgentMessage.tsx:135`) should be scheduled alongside item 3, because leaving it in place makes every other improvement unverifiable from the UI — but note it will require updating frontend tests that currently assert the fabricated values, so it cannot be done under a "keep all tests untouched" constraint.

---

## 13. Exact Files That Would Need Modification

Listed for planning only. **No modifications were made.**

| File | Symbol | Why it needs modification | Risk |
| --- | --- | --- | --- |
| `backend/app/services/embedding/factory.py` | `get_embedding_provider` (@15-17) | Silent fallback to Gemini for any unrecognised value; no offline provider option | **LOW** — 3-line function, single behaviour |
| `backend/app/services/embedding/gemini.py` | `_embed_batch_with_retry` | 404 → opaque 502; API key in URL query string; no distinct invalid-model error | **MEDIUM** — touches the only working embedding path |
| `backend/app/core/config.py` | `Settings` (@89 `GITHUB_WEBHOOK_SECRET`, @99-102 embedding, @120-138 agent) | Insecure defaults; conflicting `AGENT_DEFAULT_PROVIDER`; no cross-field validation | **MEDIUM** — settings singleton is imported everywhere |
| `backend/app/agent/models.py` | `get_chat_model_provider` (@784) | Never passes `timeout_seconds`; registers `MockChatModelProvider` as a production option | **MEDIUM** — one of only 2 production call sites |
| `backend/app/agent/models.py` | `MockChatModelProvider` (@140-258) | Fabricating provider inside the production module | **MEDIUM** — heavily used by tests; must move, not delete |
| `backend/app/agent/models.py` | `_get_openai_tools_declaration` (@552), `_get_gemini_tools_declaration` (@279) | Hardcoded 3 of 11 tools; not registry-derived; sent unconditionally | **HIGH** — changes what the model can do; affects every agent test's expected behaviour |
| `backend/app/agent/models.py` | `BaseChatModelProvider` (@120), both `ainvoke` (@418, @672) | No `astream`; no `"stream": true`; no distinct error classes per status | **HIGH** — ABC change forces all subclasses; core of real streaming |
| `backend/app/services/agent_service.py` | `stream_chat` (@287, @349, @357, @411, @436-446) | Timeout computed but unapplied; `stream_mode="updates"` cannot carry tokens; answer in one frame | **HIGH** — the production user-facing path |
| `backend/app/agent/graph.py` | `agent_node` (@37-90), `tools_node` (@164-233) | Tool errors indistinguishable from tool results; no grounded/ungrounded signal | **HIGH** — the reasoning core; every agent test depends on it |
| `backend/app/agent/multi_agent/reviewer.py` | `ReviewerAgent.execute` (@78 + `except`) | Pre-initialised `APPROVED`; parse failure → clean approval | **MEDIUM-HIGH** — security-critical; Phase 7B tests assert current behaviour |
| `backend/app/agent/multi_agent/planner.py` | fallback (@116-125) | Synthesises an empty plan on parse failure | **MEDIUM** — currently unreachable (orchestrator dead) |
| `backend/app/agent/multi_agent/coder.py` | `CoderAgent` (@34, ~@166) | Accepts a provider and never calls it; fabricates a diff | **HIGH** — requires implementing real behaviour, not editing it |
| `backend/app/agent/multi_agent/tester.py` | `TesterAgent` fallback | Never calls a model; fabricates `PASSED` | **HIGH** — same |
| `backend/app/agent/multi_agent/orchestrator.py` | `EngineeringOrchestrator` | Never constructed; unreachable from HTTP | **HIGH** — wiring it activates 5 approval gates and 4 providers at once |
| `backend/app/agent/multi_agent/config.py` | `RoleProviderConfig` | Import-time `os.getenv` bypasses `.env`; dead code | **LOW** — unused |
| `backend/app/api/v1/agent.py` | `POST /tasks` (~@578) | Documents orchestrator behaviour it does not perform | **MEDIUM** — public API contract |
| `backend/app/api/v1/github_webhooks.py` | `_run_pr_review_background`, dispatch (@106-107) | `str` → `uuid.UUID` mismatch; `ENVIRONMENT != "test"` gate makes dispatch untestable; not queued via ARQ | **MEDIUM** — Phase 7B entry point |
| `backend/app/services/github/pr_review_service.py` | `execute_review` (@~110 fallback, @120 factory, SHA check) | Hardcoded synthetic diff on fetch failure; SHA check swallowed at DEBUG | **MEDIUM-HIGH** — security-critical; audit script depends on current behaviour |
| `backend/app/workers/main.py` | `functions` (@25) | No AI/review task registered | **LOW** — additive |
| `backend/app/core/exceptions.py` | `ModelProviderException` and friends | No status-specific provider exception taxonomy | **LOW-MEDIUM** — additive; single handler at `main.py:45` |
| `backend/app/services/retrieval/hybrid.py` | `_execute_search` sparse `try/except` | Silent degradation; empty-index early `return []` gives no signal | **MEDIUM-HIGH** — 844 lines, most heavily tested service |
| `frontend/src/components/agent/AgentMessage.tsx` | @135 | `"mock-approval-123"` literal makes every UUID guard fail open | **LOW** — one line, but it is the keystone of the fabrication |
| `frontend/src/components/agent/AgentPlanView.tsx` | `MOCK_DIFF_CONTENT` (@13-25), `getMockPatch` (@27-44), `handleApprove` else-branch (@112-127), render (@312) | Fabricates diff and workspace with no backend call | **MEDIUM** — frontend tests assert these values |
| `frontend/src/components/agent/AgentDiffView.tsx` | @93/@110 guard, @288-303, @321-344 | Fabricates test run, commit SHA, PR URL | **MEDIUM** — same |
| `frontend/src/components/agent/AgentGitPanel.tsx` | @43, @56/91/125 vs @73/107/143 | `"mock-workspace-id"` fallback; status set unconditionally | **MEDIUM** — same |
| `frontend/src/types/agent.ts` | `AgentStreamEventType` (@237-275) | 38 members, zero token/delta events | **LOW-MEDIUM** — additive union members |
| `frontend/src/hooks/useAgentChat.ts` | @115, @185-201 (@194), `cancelStream` (@20-34) | Single terminal content assignment; no watchdog; cancelled → `"completed"` | **MEDIUM-HIGH** — the only streaming consumer |
| `.env.example` | @48, @50, @59 | Ships `AGENT_DEFAULT_PROVIDER=mock`; omits that `GEMINI_API_KEY` is required for embeddings regardless of chat provider; omits `GITHUB_WEBHOOK_SECRET` | **LOW** — documentation, high leverage |
| `backend/tests/conftest.py` | @9-14, @197-198 | No AI-credential neutralisation; one-hot fixture vectors; SQLite-only | **HIGH** — every test depends on it |
| `backend/tests/integration/test_retrieval_integration.py` | @131 | Real unpatched Gemini call — non-hermetic | **LOW** — isolated |
| `backend/tests/integration/test_github_pr_reviewer_api.py` | @241 | Two real `api.github.com` calls — non-hermetic | **LOW** — isolated |
| `scratch/audit_phase7b_real_world.py` | @78-79, @240-256 | In-memory SQLite; injects then asserts the same review JSON | **LOW** — untracked diagnostic script |
| `backend/pyproject.toml` | `dependencies`, `[project.optional-dependencies].dev` | LangGraph/LangChain floors (`>=0.2.0`, `>=0.3.0`) two majors behind resolved 1.x; no HTTP mocking library for provider-error tests | **LOW** — but do not upgrade during Phase 7C; pin to what is already resolved |

---

## 14. Acceptance Criteria

Phase 7C may be declared complete only when every one of the following is objectively demonstrated, with evidence recorded (log excerpt, test output, or screenshot) and no criterion satisfied by a mock.

1. **Real LLM call succeeds.** A single documented request produces an HTTP 200 from a named real provider and a named real model, with the provider and model recorded in the response and in structured logs. `AGENT_DEFAULT_PROVIDER=mock` is not reachable without an explicit override that logs a startup WARNING.
2. **Real embeddings generated.** A real repository is indexed end-to-end; `chunk_embeddings` contains rows whose `provider`/`model`/`dimension` match the configured real embedding model; vectors are not one-hot, not zero, and not fixtures; `chunk count == embedding count` validation passes on real data.
3. **pgvector retrieval returns relevant context.** A query executed against **PostgreSQL** (not SQLite) exercises `cosine_distance` and the HNSW index, returns the chunks a human reviewer agrees are relevant for a known question, and `ts_rank_cd` sparse search contributes real results without entering its exception fallback.
4. **Repository question uses real retrieved context.** For Demo A, the answer verifiably cites chunk content that appears in the `ToolMessage` payload for that request. When retrieval fails or returns nothing, the response is explicitly marked ungrounded (or errors) — never silently answered from parametric knowledge.
5. **Agent uses real model reasoning.** The tool calls in a real run are chosen by the model, not fabricated; the tool declaration sent to the provider is derived from `get_agent_tools()` so all registered tools are visible; a multi-iteration run is demonstrated within the iteration cap, and hitting the cap is signalled rather than silent.
6. **ReviewerAgent produces model-generated findings.** A real PR review yields findings traceable to a real model response. A malformed or empty model response produces an explicit failure state — **never `APPROVED` with zero findings**. The synthetic-diff fallback is gone: an unfetchable diff fails the task.
7. **GitHub PR workflow works end-to-end.** A real webhook from a real GitHub App, verified against a real `GITHUB_WEBHOOK_SECRET` (not the in-code default), produces a snapshot, a real fetched diff, AST context, retrieval, a real model review, persisted findings, and a UI render — with the SHA drift check actually executing and its result recorded.
8. **Streaming is real.** Tokens arrive incrementally: the frontend renders partial content before completion, driven by a token/delta event type that exists in `AgentStreamEventType` and an accumulating reducer in `useAgentChat`. Verifiable by observing intermediate frames on the wire, not only the final body.
9. **Provider failure is handled gracefully.** Each of missing key, invalid key, invalid model, timeout, rate limit, quota exhaustion, provider unavailable, malformed response, and embedding failure produces a distinct, meaningful, user-visible error — no swallowed exception, no generic 500, and **no fabricated fallback response**. Each case is covered by a test using HTTP transport mocking.
10. **Existing Phase 1–7B suites remain green.** 281/281 backend and 44/44 frontend still pass (adjusted only where a test asserted fabricated frontend values, with each such change explicitly justified in the PR). `ruff check .` PASS, `mypy app` PASS, Next.js production build PASS. Any real-network acceptance test is opt-in and excluded from the default run so the suite stays hermetic.
11. **No GitHub mutation occurs.** Re-verified after all changes: zero comments, zero reviews submitted, zero status checks, zero writes of any kind. The read-only guarantee is preserved.
12. **Mock mode is unambiguous.** Whenever any fabricated component is active — model, embeddings, diff, patch, workspace, test run, or git artifact — it is visibly labelled in the UI and logged at WARNING. It must be impossible to mistake a mocked run for a real one, which is the condition whose absence made this audit necessary.

---

## Appendix A — Full Mock / Fake / Stub Inventory (Part 2)

Classification: **A** Production path · **B** Test-only · **C** Development-only · **D** Dead/unused · **E** Unknown.

### Class A — production path (the ones that matter)

| # | File | Symbol | Purpose | Called by | Returns | Why it exists | Real replacement |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | `backend/app/agent/models.py` @140-258 | `MockChatModelProvider` | Fabricated chat model | `get_chat_model_provider` (@784) when `AGENT_DEFAULT_PROVIDER=mock`; injected by tests and by `scratch/audit_phase7b_real_world.py:256` | `response_override`; or `default_response`; or a fabricated `search_repository` tool call; or a hardcoded `ImplementationPlan` naming `app/api/v1/agent.py`; or `"Forge AI repository investigation complete… All codebase references verified."` | Allowed the whole application to be built and tested before a provider was reachable | `GeminiChatModelProvider` / `OpenAIChatModelProvider` — which already exist; the mock should move to `tests/` |
| A2 | `backend/app/services/github/pr_review_service.py` | synthetic diff fallback in `execute_review` | Substitute diff when GitHub fetch fails | Itself, on any exception | `"--- a/{repo}/core.py … +    # Refactored token calculation\n+    return 1"` | Let Phase 7B be developed and audited offline | A real fetched diff; failure must fail the task |
| A3 | `backend/app/agent/multi_agent/reviewer.py` | `except` → pre-initialised `APPROVED` | Guarantee a review always completes | Itself, on any parse failure | `status="APPROVED"`, `summary="Review completed. No blocking security or regression findings detected."`, zero findings | Made lifecycle tests deterministic | An explicit `REVIEW_FAILED` state |
| A4 | `backend/app/agent/multi_agent/coder.py` | `PatchService` fallback | Produce a diff without a model | `coder_node` (via the dead orchestrator) | `"+# Verified implementation"` against `app/api/v1/agent.py` | Placeholder for unimplemented code generation | A real model call using the provider it already accepts |
| A5 | `backend/app/agent/multi_agent/tester.py` | test-run fallback | Produce a green test result | `tester_node` (via the dead orchestrator) | `status="PASSED"`, `exit_code=0`, `"1 passed in 0.42s"`, `duration_ms=420` | Placeholder for unimplemented execution | Real `RunTests` tool execution |
| A6 | `frontend/src/components/agent/AgentPlanView.tsx` @13-44, @112-127 | `MOCK_DIFF_CONTENT`, `getMockPatch`, `handleApprove` else-branch | Render a patch and workspace with no backend | Rendered unconditionally @312 under `approvalStatus === "APPROVED"` | `patch-mock-ratelimit-1`, `appr-diff-mock-1`, `ws-mock-workspace-1`, `/tmp/forge_workspaces/mock_ws_8bf755`, `e1c144f8b2d41` | UI was built ahead of the write-path API | Real `ProposePatch` / workspace API responses |
| A7 | `frontend/src/components/agent/AgentMessage.tsx` @135 | `approvalId \|\| "mock-approval-123"` | Supply an approval id when absent | Every rendered agent message | a non-UUID string | Prevented undefined-prop crashes | Real approval UUID; absence must disable the action |
| A8 | `frontend/src/components/agent/AgentDiffView.tsx` @288-344 | fabricated test run / commit / PR | Complete the demo flow | @286 guard `localStatus === "APPLIED"`, set @110 even when `isUUID(patch.patch_id)` is false @93 | `"1 passed in 0.42s"`, `405e0329a174f`, `…/pull/1` | Same | Real test/commit/PR API responses |
| A9 | `frontend/src/components/agent/AgentGitPanel.tsx` @43 | `\|\| "mock-workspace-id"` | Supply a workspace id | Git panel handlers | non-UUID string; status set COMMITTED/PUSHED/CREATED @73/107/143 regardless | Same | Real workspace id |
| A10 | `backend/app/core/config.py` @89 | `GITHUB_WEBHOOK_SECRET` default | Allow startup without the secret | `verify_github_webhook_signature` | `"test-github-webhook-secret-change-in-production"` | Local development convenience | Required env var with no default |
| A11 | `backend/app/services/embedding/factory.py` @15-17 | silent `else` → Gemini | Always return a provider | `HybridSearchEngine`, `IngestionEngine` | a Gemini provider for **any** unrecognised value | Simplicity | Explicit failure on unknown values |
| A12 | `backend/app/services/embedding/gemini.py` | `embed_query` empty-text branch | Avoid an API call on empty input | `_execute_search` | `[0.0] * dimension` — a zero vector | Guard | Reject empty queries |

### Class B — test-only (legitimate, no action needed)

`backend/tests/conftest.py` fixtures including `indexed_tool_repo` (one-hot 768-d vectors @197-198), all `MockChatModelProvider` injections through `config["configurable"]["model_provider"]`, and every fixture-seeded database row. These are correct use of mocks for deterministic CI. Note only that the injection channel is the *same* one production reads.

### Class C — development-only

`.env.example:59` `AGENT_DEFAULT_PROVIDER=mock` (intended as dev convenience; in effect it makes fabrication the default for every fresh checkout). `scratch/audit_phase7b_real_world.py` (untracked diagnostic; in-memory SQLite @78-79 + injected review JSON @240-256).

### Class D — dead / unused

`backend/app/agent/multi_agent/orchestrator.py :: EngineeringOrchestrator` (never constructed in `app/`); `backend/app/agent/multi_agent/config.py :: role_provider_config` / `RoleProviderConfig` (import-time `os.getenv`, never consumed); `backend/app/agent/config.py :: AgentConfig`; `frontend/src/lib/agent-api.ts :: sendAgentMessage` (non-streaming path, never invoked); 14 of the 38 `AgentStreamEventType` members with no handler in `useAgentChat` (including `agent.pr.created`).

### Class E — unknown / unverifiable

`AGENT_GEMINI_MODEL=gemini-3.1-pro-preview` and `GEMINI_EMBEDDING_MODEL=gemini-embedding-2` — model identifier validity could not be verified (see Appendix F). The reachability and working status of every real provider is `UNKNOWN` for the same reason.

Terms searched across the repository with `--include=*.py`, `--include=*.ts`, `--include=*.tsx` scoped to `backend/app/`, `backend/tests/`, `frontend/src/`, `frontend/tests/`, `scratch/`: `Mock`, `mock`, `Fake`, `fake`, `Stub`, `stub`, `Fixture`, `fixture`, `Synthetic`, `synthetic`, `Placeholder`, `placeholder`, `TODO`, `FIXME`, `XXX`, `HACK`, `LLM`, `model`, `embedding`, `embedding_model`, `chat_model`, `completion`, `stream`, `astream`, `LangGraph`, `StateGraph`, `ReviewerAgent`, `ainvoke`, `hardcode`, `dummy`, `sample`, `example`. Notably, `TODO`/`FIXME`/`HACK` markers are essentially absent — the fabrications are not flagged as temporary anywhere in the code, which is why they have survived into Phase 7B.

## Appendix B — Part 4: Real Model Execution Diagnostic

No real model call could be executed during this audit. Reason, stated plainly so it is not mistaken for a finding about the application: the audit sandbox has **no outbound network egress** and **no installed Python dependencies**, and the project virtualenv is a Windows cp312 environment that cannot be executed from the Linux diagnostic shell. Per the task's own fallback instruction ("If not, inspect the code path and explain exactly what would need to be executed"), Part 4 is satisfied by complete code-path inspection plus the exact recipe below.

**No existing safe diagnostic mechanism reaches a real model.** There is no health-check endpoint that pings a provider, no management command, no `--real` test flag, and no smoke script. `scratch/audit_phase7b_real_world.py` injects `MockChatModelProvider` at line 256. This absence is itself a finding: there is currently **no supported way to answer "can this installation talk to a real model?"** without writing new code.

What an operator would run, from the repository root on Windows with the project venv active. These are **inspection commands for the reviewer to execute** — nothing here was run, and nothing here modifies the repository.

1. **Confirm which provider the running process would actually resolve** (proves which `.env` won, given `env_file=(".env", "../.env")` and CWD sensitivity):

   ```
   python -c "from app.core.config import settings; print(settings.AGENT_DEFAULT_PROVIDER, settings.GROQ_MODEL, settings.EMBEDDING_PROVIDER, settings.GEMINI_EMBEDDING_MODEL, settings.GEMINI_EMBEDDING_DIMENSION)"
   ```
   Run from `backend/`. Expected from the current `.env`: `groq openai/gpt-oss-120b google gemini-embedding-2 768`.

2. **Chat probe — the decisive test for Blocker 1's chat half.** A minimal `httpx` POST to `${GROQ_BASE_URL}/chat/completions` with `Authorization: Bearer ${GROQ_API_KEY}`, body `{"model": "<GROQ_MODEL>", "messages": [{"role": "user", "content": "reply with the single word: ok"}]}`. Record **only the HTTP status code** and, on non-200, the error `type`/`code` fields — never the key, never the full response if it might echo credentials. A 200 proves the active chat provider works. A 404 proves the model identifier is wrong. A 401 proves a credential problem.

3. **Embedding probe — the decisive test for the primary blocker.** POST to `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBEDDING_MODEL}:batchEmbedContents?key=${GEMINI_API_KEY}` with one request `{"model": "models/${GEMINI_EMBEDDING_MODEL}", "content": {"parts": [{"text": "hello"}]}, "taskType": "RETRIEVAL_QUERY", "outputDimensionality": 768}`. Record the status and, on 200, the returned vector **length only**. A 404 confirms the invalid-model hypothesis and pinpoints the exact cause of unreliable real-model operation. A 200 with length 768 clears the embedding model and moves the blocker to the application-logic items in Section 5.

4. **In-application chat path**, once (2) returns 200 — exercise the real graph without touching source:

   ```
   pytest tests/integration/test_agent_chat_api.py -v
   ```
   (existing suite, mock-injected — proves wiring only), then a real call through the actual factory:
   ```
   python -c "import asyncio; from app.agent.models import get_chat_model_provider; from langchain_core.messages import HumanMessage; p=get_chat_model_provider(); print(type(p).__name__, p.model_name); print(asyncio.run(p.ainvoke([HumanMessage(content='reply ok')])).content[:200])"
   ```
   Printing `type(p).__name__` is the important part: if it prints `MockChatModelProvider`, the environment is not what the operator thinks it is.

5. **In-application retrieval path**, once (3) returns 200 — requires PostgreSQL up (`docker compose up -d db`), `alembic upgrade head`, one indexed repository with an ACTIVE `RepositoryIndexVersion`, then a `HybridSearchEngine.search` call. Without an ACTIVE index version `_execute_search` returns `[]` before any embedding call is attempted, so an empty result here means "not indexed," not "retrieval broken" — a distinction the current code does not surface.

**Anticipated failure classification, by probe result:**

| Probe result | Classification | Reading |
| --- | --- | --- |
| Chat 200, embedding 200 | **APPLICATION BUG** only | Providers are fine; the unreliability is entirely Section 5's Blockers 2–5 |
| Chat 200, embedding 404 | **ENVIRONMENT / MODEL-NAME ISSUE** + **APPLICATION BUG** | `gemini-embedding-2` invalid → confirms Blocker 1; the opaque 502, missing retry, silent factory default, and absent fallback remain application bugs regardless |
| Chat 404 | **ENVIRONMENT / MODEL-NAME ISSUE** | `GROQ_MODEL` invalid |
| Chat/embedding 401 or 403 | **ENVIRONMENT / CREDENTIAL ISSUE** | Key invalid, revoked, or lacking scope — note the keys are present, so this would be validity not absence |
| Chat/embedding 429 | **ENVIRONMENT / QUOTA-BILLING ISSUE** | Chat retries 429 up to 3× (`models.py` @672 region); embeddings retry up to 4× and raise `EmbeddingQuotaExhaustedException` (429) on daily quota |
| Connection error / DNS failure | **NETWORK ISSUE** | Would also explain the PR reviewer's synthetic-diff path being taken in practice |

## Appendix C — Part 7: Agent / Tool-Call Audit

**Verdict: tool calls are REAL in execution, MOCK in declaration, and structurally incomplete.**

- **LangGraph state** — `AgentState` carries the message list, `retrieved_context`, and an iteration counter. Real. `retrieved_context` is accumulated in `tools_node` from three result shapes (`results`, `symbols`, `file_path`).
- **Tool definitions** — 11 real tool classes with real implementations: `RepositorySearch`, `SymbolSearch`, `FileViewer`, `ProposePatch`, `RunTests`, `ApplyPatch`, `CreateBranch`, `GitStatus`, `CommitChanges`, `PushBranch`, `CreatePullRequest`.
- **Registration** — `get_agent_tools()` in `backend/app/agent/tools/__init__.py`; lookup via `get_agent_tool_by_name` (linear scan). Real.
- **Declaration to the model** — **hardcoded JSON literals declaring only 3 tools**, duplicated per provider (`models.py` @279 and @552), not derived from the registry. **8 tools are invisible to the model.** The system prompts (`backend/app/agent/prompts.py` @3 `DEFAULT_AGENT_SYSTEM_PROMPT`, @32 `PLANNING_AGENT_SYSTEM_PROMPT`) likewise document only the 3 read-only tools. This is internally consistent — and it means the agent architecturally cannot choose to write code, which is why the frontend fabricates the write path.
- **Execution** — real dispatch in `tools_node` (@164), real authorization checks inside each tool, real `HybridSearchEngine` call with `session_override=db`.
- **Results back to the model** — real: `ToolMessage(content=json.dumps(res.model_dump()), tool_call_id=call_id)` @233, with content truncated to 4000 chars per chunk.
- **Model tool-calling support** — real parsing on both providers (Gemini `functionCall` parts; OpenAI/Groq `tool_calls`).
- **Retry handling** — only HTTP 429, up to 3 attempts, with `extract_retry_delay` (`models.py` @39) honouring `Retry-After`. **No retry on malformed output, empty content, or bad tool arguments.**
- **Malformed tool calls** — an unknown tool name or bad arguments produces an error `ToolMessage` that is fed back to the model. Reasonable design — but indistinguishable from a legitimate empty result, which is the root of the silent-ungrounded-answer problem.
- **Max iterations / termination** — `MAX_AGENT_ITERATIONS = 5`; `tool_router` (@139) returns END at `current_iter >= max_iterations`. Termination is silent: the user is not told reasoning was cut short.
- **Not disabled, not simulated** — with a real provider, tool calls are genuinely model-chosen. With `mock`, `MockChatModelProvider` fabricates a `search_repository` call on the first turn, which is what makes mock runs look convincingly agentic in the UI.

## Appendix D — Part 9: Error-Handling Behaviour Matrix

Current behaviour, as written. "Fabricated fallback" means the user receives something that looks like success.

| Scenario | Where it surfaces | Current behaviour | Assessment |
| --- | --- | --- | --- |
| Missing API key | provider constructor / request | Empty `Authorization` header → upstream 401 → `ModelProviderException(f"{provider} API returned status 401: …")` → `AgentExecutionException` → `ForgeAIException` handler (`main.py:45`) | Meaningful, but the message does not distinguish "not configured" from "rejected" |
| Invalid API key | request | Same as above | Meaningful; secret-safe via `sanitize_secret_text` |
| Invalid chat model | request | Upstream 404 → `ModelProviderException` with status text | Meaningful — the best-handled failure in the system |
| **Invalid embedding model** | `gemini.py` `_embed_batch_with_retry` | 404 not in the retry set → generic `ForgeAIException(status_code=502, "Gemini embedding API error (404): …")` → propagates through the tool → **error `ToolMessage`** → model answers ungrounded → **HTTP 200** | **WORST CASE — fabricated fallback.** Reads as success |
| Provider timeout | `httpx` (60 s hardcoded default) | `httpx.TimeoutException` → `ModelProviderException`. `AGENT_TIMEOUT_SECONDS` never reaches the provider; `execute_chat` wraps `wait_for` but `stream_chat` does not, so @411's `except TimeoutError` is unreachable on the production path; the frontend has no watchdog | Partially handled; **UI can hang indefinitely** |
| Rate limit (429) | both providers | Chat: retry ×3 honouring `Retry-After`; embeddings: retry ×4 | Good |
| Quota exhaustion | `gemini.py` | `EmbeddingQuotaExhaustedException` (429) | Good — the one purpose-built AI exception |
| Provider unavailable (5xx) | chat | Non-200, non-429 → immediate `ModelProviderException`, **no retry** | Meaningful but brittle |
| Provider unavailable (5xx) | embeddings | Retried (500/502/503/504) | Good |
| **Malformed model response** | `ReviewerAgent` | `except Exception` → **`APPROVED`, zero findings**, logged INFO | **Swallowed → fabricated fallback.** Security-critical |
| **Malformed model response** | `PlannerAgent` | Synthesises an empty `ImplementationPlan` | Swallowed → fabricated fallback |
| **Empty `choices`** | `OpenAIChatModelProvider.ainvoke` | Returns `AIMessage(content="")` — **no error** | Swallowed; feeds the two rows above |
| Model tool-call failure | `tools_node` | Error text as `ToolMessage`; loop continues | Reasonable, but invisible to the user |
| **Embedding failure during indexing** | `IngestionEngine` | Exception propagates; count mismatch → `"Index validation failed"` | Meaningful — indexing fails loudly. The contrast with query-time behaviour is stark |
| **No ACTIVE index version** | `_execute_search` | Returns `[]` — no error, no embedding call | **Silent ungrounded answer** |
| **Full-text search failure** | `_execute_search` | `try/except` → `"Full-text search fallback: {e}"`, continues dense-only | Silent quality degradation |
| **GitHub diff fetch failure** | `PRReviewService` | INFO log → **hardcoded synthetic diff**, review completes as `REVIEW_READY` | **Swallowed → fabricated fallback.** Security-critical |
| **SHA drift check failure** | `PRReviewService` | `logger.debug("Skipping live SHA check…")` | Swallowed at DEBUG |
| **PR review background crash** | `_run_pr_review_background` | `except Exception: logger.error(...)` and returns — task stranded mid-lifecycle, no retry, no ARQ | Logged but unrecoverable |
| Unsupported provider name | `get_chat_model_provider` | `ModelProviderException("Unsupported chat model provider: '…'. Supported: 'google', 'openai', 'groq', 'openai_compatible', 'mock'.")` | Good — and instructive that the error message advertises `mock` as a supported production provider |
| Unrecognised `EMBEDDING_PROVIDER` | `get_embedding_provider` | **Silently returns Gemini** | Bad — no error at all |
| Stream cancelled by user | `useAgentChat.cancelStream` (@20-34) | Message marked `"completed"` | Wrong state — an abandoned request is recorded as a successful one |

The pattern is consistent and worth stating directly: **failures on the ingestion/write side fail loudly; failures on the query/read side degrade into plausible output.** Six distinct paths end in a fabricated success. That asymmetry, not any single bug, is what makes the system feel unreliable with a real model while passing every test.

## Appendix E — Audit Method, Scope, and Limitations

**Method.** Static inspection of every file on the AI execution path (backend providers, factory, graph, services, retrieval, embedding, ingestion, multi-agent roles, orchestrator, GitHub PR services, webhooks, workers, exceptions, prompts, config, migrations, models; frontend hook, API client, types, and all agent components); scoped `ripgrep` sweeps for the Part 2 term list; `git` inspection to confirm working-tree state; `uv.lock` parsing for resolved dependency versions; `.env` inspection for **key names and presence only**.

**Read-only compliance.** Zero writes to any source file, test, schema, migration, route, component, environment file, or Docker configuration. No dependency was installed or upgraded. No branch was created. No provider was added. No local model was installed. Nothing was fixed. The only file created is this report.

**Working-tree state, verified.** HEAD is `c174e38`. `git diff --ignore-cr-at-eol --stat` shows **7 pre-existing modified files** (`.env.example`, `backend/app/api/router.py`, `backend/app/core/config.py`, `backend/app/models/__init__.py`, `backend/app/services/github/client.py`, `docker-compose.yml`, `frontend/src/types/agent.ts` — 96 insertions, 2 deletions) plus 18 untracked Phase 7B files. All of it predates this audit and is uncommitted Phase 7B integration work. A raw `git status` from the Linux diagnostic shell reports 74 modified files; that is a CRLF-versus-LF artifact (`core.autocrlf` unset in the sandbox, and git could not refresh its index — `warning: unable to unlink '.git/index.lock': Operation not permitted`), not evidence of change. The `--ignore-cr-at-eol` figure of 7 is the accurate one.

**Limitations, stated so no conclusion is over-read.**

1. **No outbound network egress** in the audit environment. No live provider call was made. Every `Reachable` and `Working` cell in Section 4 is therefore honestly `UNKNOWN` rather than inferred.
2. **Model identifiers could not be validated.** `ai.google.dev` was unreachable (`cowork-egress-blocked`) and web search was unavailable. `gemini-3.1-pro-preview` and `gemini-embedding-2` are reported as **UNVERIFIED** — not as invalid. This audit deliberately does not assert they are wrong; it asserts that the application cannot tell you either way, which is the actionable finding.
3. **The test suites were not executed.** No Python dependencies are installed in the diagnostic environment and the project virtualenv is Windows cp312. The 281/44 baselines are taken as given from the task statement; the static count of collected items is 282, a one-item discrepancy noted in Section 9 and not resolved.
4. **`.env` was inspected for key names and presence only.** No secret value was read into context or printed. Values reported are non-secret configuration only (provider names, model names, URLs, numeric settings). An early emptiness check misreported three variables as configured because `.env` uses CRLF terminators (values were `"\r"`); corrected by stripping `\r` and trailing whitespace, which reclassified `OPENAI_COMPATIBLE_*` as MISSING.
5. **Line numbers** are as observed at HEAD `c174e38` with the 7 uncommitted modifications in place. A few are approximate and marked `~`.

---

PHASE 7C AUDIT VERDICT: PARTIALLY REAL

RECOMMENDED NEXT ACTION: Before writing any code, run the two read-only probes in Appendix B against the configured Groq chat endpoint and the `gemini-embedding-2` embedding endpoint and record the exact HTTP status codes — because whether Phase 7C begins with a one-line model-identifier correction or a full provider-configuration refactor depends entirely on those two results, and every other finding in this report is downstream of them.
