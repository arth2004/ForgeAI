# Google Gemini Chat Model Provider Documentation

This document describes the configuration, architecture, function calling integration, and migration procedures for the Google Gemini LLM provider in Forge AI.

---

## 1. Overview & Active Model

Forge AI uses **`gemini-3.1-pro-preview`** as its primary Google Gemini model for code reasoning and repository question answering in Phase 4.

* **Model Identifier**: `gemini-3.1-pro-preview`
* **API Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent`
* **Supported Capabilities**:
  * Multi-turn chat reasoning via LangGraph
  * Function / Tool calling (`tools.functionDeclarations`)
  * `systemInstruction` support for codebase reasoning contracts
  * High-context token capacity with low latency

---

## 2. Why `gemini-3.1-pro-preview`

1. **API Availability**: Older legacy/preview identifiers (such as `gemini-2.5-pro` or regional flash variants) return `404 NOT_FOUND` on Google's API.
2. **Function Calling Support**: `gemini-3.1-pro-preview` natively supports `functionDeclarations` and returns structured `functionCall` candidate parts required by Forge AI's repository tool loop.
3. **Grounding Accuracy**: Provides superior reasoning when inspecting AST symbols, source code files, and hybrid RRF retrieval evidence.

---

## 3. Configuration Path

Configuration follows an authoritative 4-tier resolution hierarchy:

```text
Environment Variable (AGENT_GEMINI_MODEL in .env / Container)
        ↓
FastAPI Settings (backend/app/core/config.py)
        ↓
AgentConfig (backend/app/agent/config.py)
        ↓
GeminiChatModelProvider (backend/app/agent/models.py)
        ↓
Google Gemini HTTPS API (v1beta/models/gemini-3.1-pro-preview:generateContent)
```

### Key Settings

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `AGENT_DEFAULT_PROVIDER` | `google` | Primary LLM provider (`google`, `openai`, `mock`) |
| `AGENT_GEMINI_MODEL` | `gemini-3.1-pro-preview` | Default Google Gemini model |
| `GEMINI_API_KEY` | *(secret)* | Google AI Studio API Key |
| `AGENT_TEMPERATURE` | `0.2` | Sampling temperature for deterministic code reasoning |
| `AGENT_MAX_TOKENS` | `4096` | Output token generation limit |
| `AGENT_TIMEOUT_SECONDS` | `60.0` | HTTP request timeout |

---

## 4. Function Calling Architecture

The provider declares the Phase 4 repository tools directly in the request payload:

```json
{
  "contents": [...],
  "systemInstruction": {"parts": [{"text": "..."}]},
  "tools": [
    {
      "functionDeclarations": [
        {
          "name": "search_repository",
          "description": "Searches repository code and documentation using dense and sparse hybrid retrieval.",
          "parameters": {
            "type": "OBJECT",
            "properties": {
              "query": {"type": "STRING", "description": "Search query text."}
            },
            "required": ["query"]
          }
        },
        {
          "name": "search_symbol",
          "description": "Searches AST symbol declarations in the repository.",
          "parameters": {
            "type": "OBJECT",
            "properties": {
              "symbol_name": {"type": "STRING", "description": "The symbol identifier to search for."}
            },
            "required": ["symbol_name"]
          }
        },
        {
          "name": "get_file",
          "description": "Retrieves repository file content with optional line slicing.",
          "parameters": {
            "type": "OBJECT",
            "properties": {
              "file_path": {"type": "STRING", "description": "Repository relative file path."}
            },
            "required": ["file_path"]
          }
        }
      ]
    }
  ]
}
```

### Execution Loop

```text
User Query
    ↓
GeminiChatModelProvider.ainvoke()
    ↓
Gemini returns functionCall candidate (e.g. search_repository)
    ↓
LangGraph tool_router detects tool_calls
    ↓
tools_node executes tool against pgvector / repository index
    ↓
ToolMessage with functionResponse payload appended
    ↓
GeminiChatModelProvider.ainvoke() receives ToolMessage
    ↓
Final grounded AIMessage generated and streamed to user
```

---

## 5. Error Sanitization & Security

1. **Secret Redaction**: All API keys (`AIza...`, `sk-...`) are automatically stripped by `sanitize_secret_text()` before entering error logs or client responses.
2. **Diagnostic Error Cards**: If an invalid model or quota exhaustion occurs, the backend raises `ModelProviderException` which the frontend formats into a structured troubleshooting notification rather than dumping raw JSON.

---

## 6. Testing Strategy

* **Deterministic Automated Tests**: All unit and integration tests use `MockChatModelProvider` or mocked HTTP fixtures. No real API keys are required to pass `pytest`.
* **Static Fallback Protection**: Tests in `test_agent_foundation.py` verify that `AGENT_GEMINI_MODEL` defaults to `gemini-3.1-pro-preview` and explicitly forbid stale fallbacks (`gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.5-pro`).
* **Live Smoke Testing**:
  * Check greeting: `"hi"` $\rightarrow$ Direct text response.
  * Check repository reasoning: `"Where is authentication implemented?"` $\rightarrow$ Model invokes `search_repository`, receives tool output, and returns grounded citations.

---

## 7. Model Migration Procedure

To update or migrate the Gemini model in future versions:

1. Update `AGENT_GEMINI_MODEL` default in `backend/app/core/config.py`.
2. Update `.env.example` and your local `.env`.
3. Update `test_agent_foundation.py` assertions.
4. Run full backend pytest (`python -m pytest`) and Next.js build (`npm run build`).
