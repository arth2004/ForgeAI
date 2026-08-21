# Multi-Provider LLM Architecture & Resilience Guide

This document specifies the decoupled multi-provider LLM integration, rate-limit resilience, function calling protocol, and failure handling architecture for Forge AI.

---

## 1. Provider Abstraction Architecture

Forge AI enforces an absolute separation of concerns between agent reasoning graphs, service orchestration, and LLM vendor APIs:

```text
User / API Request
        ↓
   AgentService (backend/app/services/agent_service.py)
        ↓
   LangGraph Reasoning Graph (backend/app/agent/graph.py)
        ↓
   BaseChatModelProvider Interface (backend/app/agent/models.py)
        ↓
   ┌───────────────────────┬───────────────────────┬───────────────────────┐
   │                       │                       │                       │
   ▼                       ▼                       ▼                       ▼
GeminiChatModelProvider  OpenAIChatModelProvider  OpenAIChatModelProvider  MockChatModelProvider
(provider: "google")     (provider: "groq")      (provider: "openai_      (provider: "mock")
                                                  compatible" / "openai")
```

### Architectural Guarantees:
1. **Decoupled Workflow Nodes**: Neither `graph.py` nor `AgentService` contains vendor-specific conditionals, URLs, or payload translators.
2. **Standard Message Protocol**: All providers consume and emit standard LangChain `BaseMessage` objects (`HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`).
3. **Structured Tool Contracts**: Tool declarations (`search_repository`, `search_symbol`, `get_file`) are declared within the provider classes using standard vendor JSON schemas.
4. **Configuration-Driven Provider Selection**: Provider selection is strictly driven by application settings / environment variables.

> [!IMPORTANT]
> **Automatic provider failover is NOT currently enabled.** Provider selection is static and configuration-driven at startup via `AGENT_DEFAULT_PROVIDER`.

---

## 2. Supported Providers & Configuration

### A. Groq (Active Default)
Groq provides low-latency inference on LPUs (Language Processing Units) with an OpenAI-compatible interface.
- **Provider Identifier**: `groq`
- **Configured Model**: `openai/gpt-oss-120b` (passed exactly without hardcoding or substitution)
- **Base URL**: `https://api.groq.com/openai/v1`
- **Environment Variables**:
  ```env
  AGENT_DEFAULT_PROVIDER=groq
  GROQ_API_KEY=gsk_your_actual_key_here
  GROQ_MODEL=openai/gpt-oss-120b
  GROQ_BASE_URL=https://api.groq.com/openai/v1
  ```

### B. Google Gemini
Direct HTTPS integration using Google AI Studio REST API.
- **Provider Identifier**: `google` (or `gemini`)
- **Configured Model**: `gemini-3.1-pro-preview`
- **API Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent`
- **Environment Variables**:
  ```env
  AGENT_DEFAULT_PROVIDER=google
  GEMINI_API_KEY=AIza_your_actual_key_here
  AGENT_GEMINI_MODEL=gemini-3.1-pro-preview
  ```

### C. Standard OpenAI
Direct HTTPS integration with OpenAI API.
- **Provider Identifier**: `openai`
- **Configured Model**: `gpt-4o`
- **Base URL**: `https://api.openai.com/v1`
- **Environment Variables**:
  ```env
  AGENT_DEFAULT_PROVIDER=openai
  OPENAI_API_KEY=sk-your_actual_key_here
  AGENT_OPENAI_MODEL=gpt-4o
  ```

### D. Generic OpenAI-Compatible (Cerebras, NVIDIA NIM, OpenRouter, GitHub Models)
Universal adapter for any third-party or self-hosted LLM endpoint conforming to `/v1/chat/completions`.
- **Provider Identifier**: `openai_compatible`
- **Environment Variables**:
  ```env
  AGENT_DEFAULT_PROVIDER=openai_compatible
  OPENAI_COMPATIBLE_API_KEY=your_key_here
  OPENAI_COMPATIBLE_BASE_URL=https://api.cerebras.ai/v1
  OPENAI_COMPATIBLE_MODEL=llama-3.3-70b
  ```

### E. Deterministic Mock Provider
Offline mock for deterministic unit testing with zero API calls.
- **Provider Identifier**: `mock`
- **Environment Variables**:
  ```env
  AGENT_DEFAULT_PROVIDER=mock
  ```

---

## 3. Quota & Rate-Limit Specifications

Rate limits vary significantly across providers, models, and account tiers:

| Provider | Model | Requests / Min (RPM) | Requests / Day (RPD) | Tokens / Min (TPM) | Tokens / Day (TPD) |
|---|---|---|---|---|---|
| **Groq (Free Tier)** | `openai/gpt-oss-120b` | 30 RPM | 1,000 RPD | 8,000 TPM | 200,000 TPD |
| **Groq (Free Tier)** | `llama-3.1-8b-instant` | 30 RPM | 14,400 RPD | 6,000 TPM | 500,000 TPD |
| **Google Gemini (Free)** | `gemini-3.1-pro-preview` | 15 RPM | 500 RPD | 32,000 TPM | N/A |
| **Cerebras (Free Tier)** | `llama-3.3-70b` | 30 RPM | Unlimited | 60,000 TPM | Unlimited |
| **NVIDIA NIM (Free)** | `meta/llama-3.3-70b-instruct` | 40 RPM | No daily cap | High | High |

> [!NOTE]
> **Distinction Between Quotas**:
> - **Provider-level limits**: Max concurrent connections and IP rate limiters enforced by the edge proxy.
> - **Model-specific limits**: TPM (Tokens Per Minute) and RPD (Requests Per Day) caps assigned per model family (e.g. 120B models have lower TPM thresholds than 8B models).
> - **Organization-level limits**: Aggregate credit balance or shared project quotas.

---

## 4. 429 Rate-Limit Retry Engine

When executing multi-turn tool loops, burst token volume can momentarily saturate TPM rate limits. The provider layer incorporates a resilient retry engine:

```text
Request Attempt 1
       ↓
Status == 429? ─── No ───► Return Response / Handle Status
       │ (Yes)
Extract Retry Delay (Priority Hierarchy)
       │ 1. Retry-After header
       │ 2. x-ratelimit-reset-* headers
       │ 3. Provider JSON retry metadata
       │ 4. Parsed error text ("try again in X.Xs")
       │ 5. Bounded exponential backoff + jitter
       ↓
Pause via asyncio.sleep(wait_seconds) (capped at 10.0s)
       ↓
Attempt 2 (up to Max 3 Retries)
       ↓
Exhausted? ───► Raise ModelProviderException(status_code=429)
```

### Non-Retryable Error Rules:
The following status codes are classified as permanent client/config errors and **fail immediately without retries**:
- `400 Bad Request` (e.g. Malformed tool declaration)
- `401 Unauthorized` (e.g. Invalid API key)
- `403 Forbidden` (e.g. Organization scope or permission denial)
- `404 Not Found` (e.g. Non-existent model ID)
- `422 Unprocessable Entity`

---

## 5. Tool Calling Protocol & Multi-Turn Sequence

All providers implement identical tool schemas:
1. `search_repository`: Hybrid dense + sparse vector search with Reciprocal Rank Fusion (RRF).
2. `search_symbol`: AST symbol definition index lookup.
3. `get_file`: Source file retrieval with optional line-range slicing.

### Execution Cycle:
```text
User Question
     ↓
agent_node: provider.ainvoke(messages)
     ↓
AIMessage(tool_calls=[{"id": "call_123", "name": "search_repository", "args": {...}}])
     ↓
tool_router -> tools_node: executes RepositorySearchTool
     ↓
ToolMessage(tool_call_id="call_123", content="{...}") appended to state["messages"]
     ↓
agent_node: provider.ainvoke(updated_messages)
     ↓
AIMessage(content="Final grounded answer with code citations.")
     ↓
END
```

---

## 6. Observability & Security Compliance

### Structured Logging:
Every LLM call logs:
- `provider`: Provider identifier (`groq`, `google`, `openai`, `openai_compatible`)
- `model`: Exact model identifier requested
- `duration_ms`: Wall-clock latency in milliseconds
- `retries_used`: Number of 429 retries required before success (0–3)
- `tool_calls_count`: Number of tool declarations emitted by the model

### Secret Redaction Guarantee:
All error messages, exception payloads, and log entries pass through `sanitize_secret_text()` which redacts:
- Google AI Studio keys (`AIza...`)
- OpenAI keys (`sk-...`)
- Groq keys (`gsk_...`)
- NVIDIA keys (`nvapi-...`)
- Cerebras keys (`csk-...`)
- Authorization Bearer tokens (`Bearer eyJ...`)
- URL query parameters (`key=...`)
