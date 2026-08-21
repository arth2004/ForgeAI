# Forge AI — Phase 5: Final Architecture & Safety Specification

## 1. Executive Architecture Summary

Forge AI Phase 5 establishes an enterprise-grade, bounded, and human-in-the-loop controlled AI software engineering platform. It enables intelligent autonomous repository investigation, structured planning, isolated workspace creation, safe patch synthesis, sandboxed test execution, and controlled Git commit, branch push, and GitHub Pull Request integration.

```
+-------------------------------------------------------------------------------+
|                             USER CHAT / IDE                                   |
+---------------------------------------+---------------------------------------+
                                        | (SSE / REST)
                                        v
+-------------------------------------------------------------------------------+
|                       FORGE AI AGENT CORE & ROUTER                            |
|  - Provider Abstraction (Groq, Gemini, OpenAI, OpenAI-Compatible, Mock)       |
|  - State Machine & Session Isolation                                          |
|  - Tool Registry & Read/Write Tool Isolation                                  |
+-------------------+-----------------------------------+-----------------------+
                    |                                   |
         (Read Only Intelligence)             (State Mutation Operations)
                    v                                   v
+---------------------------------------+   +-----------------------------------+
|     PHASE 3 REPOSITORY ENGINE         |   |    AGENT WORKSPACE & WORKTREE     |
| - AST Tree-Sitter Symbols             |   | - Isolated Temporary Directory    |
| - Code Chunking & Embeddings          |   | - Base Commit Grounding           |
| - Hybrid BM25 / Vector Retrieval      |   | - Transactional Rollback Engine   |
+---------------------------------------+   +-----------------+-----------------+
                                                              |
                                                              v
+-------------------------------------------------------------------------------+
|                     HUMAN-IN-THE-LOOP (HITL) APPROVAL GATES                   |
|                                                                               |
|   [Gate 1: PLAN]   --> Human approves structured Implementation Plan          |
|   [Gate 2: DIFF]   --> Human approves server-generated unified diff preview   |
|   [Gate 3: COMMIT] --> Human approves local Git commit execution              |
|   [Gate 4: PUSH]   --> Human approves non-force push to remote branch         |
|   [Gate 5: PR]     --> Human approves GitHub Pull Request creation            |
+---------------------------------------+---------------------------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
+----------------------------------+         +----------------------------------+
|    SANDBOX TEST RUNNER (gVisor)  |         |   AUTHENTICATED GIT / GITHUB     |
| - --network=none                 |         | - Server-Side In-Memory Tokens   |
| - Max 2.0 vCPU, 2048 MB RAM      |         | - Zero Token Leakage / Scrubbed  |
| - 120s Timeout & Resource Bounds |         | - Protected Branch Defenses      |
| - Secret Redaction & Log Scrub   |         | - Sanitized PR Markdown          |
+----------------------------------+         +----------------------------------+
```

---

## 2. Invariant & Security Model

| Security Dimension | Enforced Invariant | Implementation Mechanism |
| :--- | :--- | :--- |
| **Autonomy Boundaries** | Zero direct remote mutations from LLM tool calls alone | `ApplyPatchTool`, `CommitChangesTool`, `PushBranchTool`, and `CreatePullRequestTool` return `APPROVAL_REQUIRED`. |
| **Approval Authoritativeness** | Approvals must be authenticated database records in `APPROVED` status | `AgentApproval` checked server-side prior to mutation execution. Never trusts tool inputs or frontend state. |
| **Credential Isolation** | GitHub App tokens never exposed to LLM, state, logs, or UI | Generated server-side, stored strictly in-memory during request, scrubbed from stdout/stderr. |
| **Workspace Isolation** | Ephemeral worktree directories per session | Workspaces in `/tmp/forge_workspaces/{id}`, 60-min TTL reaper, cross-tenant 403 access control. |
| **Patch Safety** | Atomic application, canonical paths, drift prevention | Canonical path validator, SHA256 disk verification (`PATCH_CONFLICT`), AST-safe unified diff synthesis, automatic rollback. |
| **Sandboxed Execution** | Complete isolation of test/lint commands | Containerized execution, `--network=none`, memory/CPU caps, shell injection parsing, ANSI scrubbing. |
| **Git Safety** | Non-force push to feature branches only | Strict block on `main`, `master`, `production`, `staging`, `develop`, `release/*`; `--force` prohibited. |

---

## 3. Approval Chain Lifecycle

1. **Gate 1 (`ApprovalType.PLAN`)**:
   - Agent drafts `ImplementationPlan` (problem statement, affected files, approach, test strategy).
   - Graph transitions to `AWAITING_APPROVAL`.
   - Human reviews plan and approves via `POST /api/v1/agent/approvals/{id}/resolve`.
2. **Gate 2 (`ApprovalType.DIFF`)**:
   - Agent proposes structured `PatchFile` list via `propose_patch`.
   - Server validates path bounds and hash drift, generates unified diff, and records pending `DIFF` approval.
   - Human reviews visual diff in UI and approves via `POST /api/v1/agent/patches/{id}/approve`.
   - `POST /api/v1/agent/patches/{id}/apply` applies patch atomically with rollback capability.
3. **Sandboxed Verification**:
   - Declarative `TestCommand` (e.g. `pytest`, `ruff`, `npm_test`) runs in isolated sandbox via `POST /api/v1/agent/workspaces/{id}/tests`.
4. **Gate 3 (`ApprovalType.COMMIT`)**:
   - Human reviews test report and approves commit.
   - `POST /api/v1/agent/workspaces/{id}/commit` creates local `AgentCommit` with static author identity (`agent@forge.ai`).
5. **Gate 4 (`ApprovalType.PUSH`)**:
   - Human approves remote push.
   - `POST /api/v1/agent/workspaces/{id}/push` executes non-force push using short-lived in-memory token.
6. **Gate 5 (`ApprovalType.PR_CREATE`)**:
   - Human reviews synthesized PR title/body.
   - `POST /api/v1/agent/pulls/{workspace_id}/create` creates authenticated GitHub Pull Request.

---

## 4. Multi-Provider Independence

The Phase 5 code modification, workspace, patching, and Git layers are 100% decoupled from the underlying LLM provider. The system transparently supports:
- **Groq** (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`)
- **Google Gemini** (`gemini-3.1-pro-preview`)
- **OpenAI** (`gpt-4o`, `o3-mini`)
- **OpenAI-Compatible Providers** (Local vLLM, Ollama, DeepSeek)
- **Mock Provider** (Deterministic CI/CD unit testing)
