# Forge AI — Phase 5: Repository-Aware Software Engineering Agent Architecture & Safety Design

## 1. Executive Summary

Forge AI Phase 1 through Phase 4 established a robust, repository-grounded intelligence platform capable of deep codebase understanding, semantic Tree-sitter AST parsing, hybrid dense/sparse vector retrieval (RRF), and multi-turn conversational reasoning over indexed codebases (v0.4.0).

**Phase 5 evolves Forge AI from a read-only codebase reasoning assistant into a controlled, safe, and verifiable software engineering agent.**

The agent will be capable of autonomously analyzing user issues, proposing structured plans, modifying code within isolated ephemeral workspaces, executing local test suites, reviewing diffs, and requesting explicit human approval prior to mutating persistent repository branches or opening GitHub Pull Requests.

> [!IMPORTANT]
> **Strict Safety Contract**: Code modification and test execution introduce stateful side effects, security risks, and unpredictable LLM behavior. Forge AI Phase 5 enforces absolute containment: **zero autonomous persistent writes**, **mandatory human approval gates for dangerous operations**, **ephemeral container sandboxes with restricted network access**, **patch-based atomic modifications**, and **cryptographic tenant credential isolation**.

---

## 2. Goals & Non-Goals

### Goals
1. **Controlled Repository Modification**: Enable agents to safely create, modify, and delete files using structured patch contracts rather than raw file overwrites.
2. **Deterministic Workspace Isolation**: Ensure all agent-driven code changes, linters, and test executions occur inside ephemeral, resource-constrained sandbox workspaces isolated from the host server.
3. **Mandatory Human-in-the-Loop (HITL) Approval**: Require explicit, authenticated user approval before applying patches, pushing branches, or opening pull requests.
4. **Automated Verification Loop**: Allow agents to iterate on code modifications by running allowlisted linters, compilers, and test runners within the sandbox, observing exit codes and stdout/stderr to fix regressions.
5. **Clean Rollback Semantics**: Provide transactional, one-click rollbacks to restore workspaces to clean states if tests fail or if the user rejects proposed changes.
6. **Multi-Tenant Security & Secret Protection**: Guarantee that sandboxes cannot access database credentials, backend `.env` variables, host Docker sockets, or other tenant workspaces.

### Non-Goals
1. **Autonomous Production Deployment**: The agent will not push directly to `main`/`master` branches or deploy to production infrastructure.
2. **Arbitrary Unrestricted Shell Access**: The agent will not be given arbitrary root shell access or unconstrained network sockets.
3. **Real-Time Collaborative Multi-User Editing**: Phase 5 focuses on single-user agent sessions with exclusive workspace locks.
4. **Immediate Code Writing Implementation (Phase 5A Scope)**: Phase 5A is strictly limited to architectural design, security boundaries, and ADRs. Code implementations belong to Phase 5B.

---

## 3. Current Architecture vs. Future Architecture

### Current Phase 4 Baseline (Read-Only Reasoning)
```text
User / API Request (JWT Auth)
       ↓
AgentService (backend/app/services/agent_service.py)
       ↓
LangGraph Reasoning Loop (START -> agent_node -> tool_router -> tools_node -> END)
       ↓
Read-Only Tools (search_repository, search_symbol, get_file)
       ↓
PostgreSQL 16 / pgvector / Tree-sitter Indexes (Phase 3 Intelligence)
       ↓
Grounded Answer + Citations (SSE Stream)
```

### Future Phase 5 Target Architecture (Controlled Modification & Verification)
```text
Issue / User Task
       ↓
[Phase 4 Read Tools] ──► Understand Codebase & Locate Symbols
       ↓
LangGraph Planning Node ──► Generate Structured Implementation Plan
       ↓
[HUMAN APPROVAL GATE 1] ──► User Reviews Plan & Approves Investigation / Workspace Creation
       ↓
Workspace Manager ──► Provision Ephemeral AgentWorkspace (Git Worktree + Isolated Sandbox)
       ↓
┌─────────────────────────────── AGENT ITERATION LOOP ───────────────────────────────┐
│                                                                                     │
│  agent_node ──► Propose Structured Patch (file_path, old_hash, diff, explanation)  │
│       ↓                                                                             │
│  [HUMAN APPROVAL GATE 2] ──► User Reviews Visual Diff (or auto-approved in sandbox) │
│       ↓                                                                             │
│  tools_node (apply_patch) ──► Apply atomic patch inside AgentWorkspace              │
│       ↓                                                                             │
│  tools_node (run_tests / run_linter) ──► Execute inside Container Sandbox           │
│       ↓                                                                             │
│  Inspect Exit Code & Test Output ──► If tests fail, iterate & refine patch          │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
       ↓
[HUMAN APPROVAL GATE 3] ──► Final Diff Review (Files Changed, Lines +/- , Test Report)
       ↓ (Approved)
Git / GitHub Manager ──► Create Branch `forge/{session-id}` -> Commit -> Push -> Open PR
       ↓
Workspace Cleanup ──► Destroy Ephemeral Sandbox & Prune Worktree
```

---

## 4. Read vs. Write Boundary Separation

To ensure system integrity, Forge AI enforces an architectural partition between read and write operations:

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             READ OPERATIONS (Safe / Fast)                        │
├──────────────────────┬─────────────────────────┬─────────────────────────────────┤
│ Tool Name            │ Scope                   │ Execution Target                │
├──────────────────────┼─────────────────────────┼─────────────────────────────────┤
│ `search_repository`  │ Vector + Lexical Search │ PostgreSQL pgvector / tsvector  │
│ `search_symbol`      │ AST Symbol Index        │ PostgreSQL code_symbols DB      │
│ `get_file`           │ Bounded File Slicing    │ In-memory / Cached Repo Tree    │
└──────────────────────┴─────────────────────────┴─────────────────────────────────┘
                                       │
                    [ARCHITECTURAL AUTHORIZATION BOUNDARY]
                                       │
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            WRITE OPERATIONS (Stateful / Gated)                   │
├──────────────────────┬─────────────────────────┬─────────────────────────────────┤
│ Tool Category        │ Tool Name               │ Execution Target                │
├──────────────────────┼─────────────────────────┼─────────────────────────────────┤
│ Workspace Mutation   │ `propose_patch`         │ Transient AgentState / Review UI│
│                      │ `apply_patch`           │ Ephemeral AgentWorkspace        │
│                      │ `revert_patch`          │ Ephemeral AgentWorkspace        │
├──────────────────────┼─────────────────────────┼─────────────────────────────────┤
│ Sandbox Execution    │ `run_tests`             │ Ephemeral Docker Sandbox        │
│                      │ `run_linter`            │ Ephemeral Docker Sandbox        │
│                      │ `run_build`             │ Ephemeral Docker Sandbox        │
├──────────────────────┼─────────────────────────┼─────────────────────────────────┤
│ Version Control (Git)│ `create_branch`         │ Ephemeral AgentWorkspace        │
│                      │ `commit_changes`        │ Ephemeral AgentWorkspace        │
│                      │ `push_branch`           │ Remote GitHub Repository        │
├──────────────────────┼─────────────────────────┼─────────────────────────────────┤
│ GitHub Orchestration │ `create_pull_request`   │ GitHub REST API (v3)            │
└──────────────────────┴─────────────────────────┴─────────────────────────────────┘
```

---

## 5. Tool Safety Model & Hierarchy

The agent runtime classifies all tools into a strict safety tier hierarchy:

```text
               Tier 0: READ-ONLY (Zero Side-Effects)
               [search_repository, search_symbol, get_file]
                                  │
                                  ▼
               Tier 1: WORKSPACE MUTATION (Sandbox-Contained)
               [propose_patch, apply_patch, revert_patch]
                                  │
                                  ▼
               Tier 2: CODE EXECUTION (Sandbox-Contained)
               [run_tests, run_linter, run_build]
                                  │
                                  ▼
               Tier 3: PERSISTENT GIT OPERATIONS (Remote-Mutating)
               [create_branch, commit_changes, push_branch]
                                  │
                                  ▼
               Tier 4: GITHUB COLLABORATION (Upstream PR)
               [create_pull_request]
```

### Safety Rules:
1. **Tier 0 (Read-only)**: Unrestricted during reasoning turns within configured `MAX_AGENT_ITERATIONS`.
2. **Tier 1 & Tier 2 (Sandbox writes/execution)**: Permitted only within an active, provisioned `AgentWorkspace`. Cannot touch host OS files.
3. **Tier 3 & Tier 4 (Git/GitHub writes)**: Strictly blocked until **Human Approval Gate** returns `APPROVED` with an authenticated cryptographic signature from the session owner.

---

## 6. Granular Permission Model

Capabilities are evaluated using an Attribute-Based Access Control (ABAC) matrix across six hierarchical scopes:

$$\text{Authorized} = \text{UserPerm} \land \text{OrgPerm} \land \text{ProjectPerm} \land \text{RepoPerm} \land \text{BranchPerm} \land \text{SessionPerm}$$

### Permission Scopes:
- `READ_ONLY`: Can query repository intelligence, search symbols, and inspect files.
- `PROPOSE_CHANGES`: Can prompt the agent to generate implementation plans and patch proposals.
- `APPLY_CHANGES`: Can create ephemeral sandboxes and apply patches within the workspace.
- `RUN_COMMANDS`: Can trigger sandboxed test execution, linters, and build scripts.
- `GIT_WRITE`: Can create feature branches (`forge/*`) and commit code changes.
- `PR_CREATE`: Can authorize opening GitHub Pull Requests upstream.

### Enforcement Matrix:

| Role / Permission | READ_ONLY | PROPOSE_CHANGES | APPLY_CHANGES | RUN_COMMANDS | GIT_WRITE | PR_CREATE |
|---|---|---|---|---|---|---|
| **Viewer** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Contributor** | ✅ Yes | ✅ Yes | ✅ Yes (Sandbox) | ✅ Yes (Sandbox) | ❌ No | ❌ No |
| **Developer** | ✅ Yes | ✅ Yes | ✅ Yes (Sandbox) | ✅ Yes (Sandbox) | ✅ Yes (Feature) | ✅ Yes (Draft PR) |
| **Maintainer / Admin** | ✅ Yes | ✅ Yes | ✅ Yes (Sandbox) | ✅ Yes (Sandbox) | ✅ Yes (All) | ✅ Yes (Full PR) |

---

## 7. Human Approval Gate & Review Workflow

No dangerous operation (remote git push, persistent branch mutation, or pull request creation) can occur autonomously.

### Approval Gate Workflow:
```text
Agent Emits: "Proposed Solution Ready for Review"
      ↓
API Emits SSE Event: agent.approval_required
      {
        "approval_id": "appr-550e8400-e29b-41d4-a716-446655440000",
        "action": "git.push_and_pr",
        "target_branch": "forge/issue-102-auth-fix",
        "files_changed": [
          {"path": "backend/app/core/security.py", "status": "modified", "additions": 14, "deletions": 3}
        ],
        "diff": "--- a/backend/app/core/security.py\n+++ b/backend/app/core/security.py\n...",
        "test_results": {"passed": 149, "failed": 0, "duration_s": 12.4},
        "risk_level": "LOW"
      }
      ↓
Frontend Displays Interactive Review Modal
      ├── Visual Split / Unified Monaco Diff
      ├── Test & Linter Execution Summary
      ├── Commit Message & PR Description Draft
      └── Action Buttons: [Approve & Create PR] [Request Changes] [Reject & Discard]
      ↓
User Action:
      ├── APPROVE ──► POST /api/v1/agent/approvals/{id}/approve -> Triggers Git push & PR creation
      ├── REQUEST_CHANGES ──► POST /api/v1/agent/approvals/{id}/changes -> Agent re-enters iteration loop
      └── REJECT ──► POST /api/v1/agent/approvals/{id}/reject -> Triggers Rollback & Workspace Destruction
```

---

## 8. Ephemeral Workspace Model & Lifecycle

Every code modification session is bound to an isolated, temporary **AgentWorkspace**.

```text
Repository (PostgreSQL / GitHub Origin)
    ↓
AgentWorkspace
    ├── id: UUID
    ├── session_id: UUID
    ├── user_id: UUID
    ├── repository_id: UUID
    ├── base_branch: "main"
    ├── working_branch: "forge/session-7f3b"
    ├── worktree_path: "/tmp/forge_workspaces/ws-7f3b"
    ├── sandbox_container_id: "docker://sandbox-7f3b"
    └── status: WorkspaceStatus
```

### Workspace Lifecycle State Machine:
```text
  [CREATED] (DB record initialized)
      ↓
  [PREPARED] (Git worktree checked out + dependencies cached)
      ↓
  [MODIFIED] (Patches applied to local worktree)
      ↓
  [TESTING] (Tests/linters running in container sandbox)
      ↓
  [REVIEW] (Diff prepared, awaiting human approval)
      ├── [REJECTED] ──► [ROLLED_BACK] ──► [DESTROYED]
      └── [APPROVED] ──► [COMMITTED] ──► [PUSHED] ──► [DESTROYED]
```

### Concurrency & Repository Locking:
- **Workspace-Level Isolation**: Multiple users working on the same repository receive separate, isolated `AgentWorkspace` instances backed by distinct Git worktrees.
- **Branch-Level Write Lock**: Only one active agent session may hold a write lock on a specific target branch (`forge/{branch_name}`).
- **TTL Expiration**: Workspaces have a strict Time-To-Live (e.g. 60 minutes). Inactive workspaces are automatically cleaned up, and their containers are purged.

---

## 9. Sandbox Architecture & Resource Isolation

Future code execution (test runners, linters, compilers) must **never** run on the Forge AI backend host.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                FORGE AI HOST                                    │
│                                                                                 │
│  FastAPI Backend ──(Docker Engine API / gVisor)──► Ephemeral Sandbox Container   │
│                                                     │                           │
│                                                     ├── Non-root user (forge:1000)│
│                                                     ├── Read-only rootfs        │
│                                                     ├── Tempfs /tmp & /workspace │
│                                                     ├── No network access       │
│                                                     └── Resource limits enforced│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Sandbox Resource Envelopes:
- **Isolation Technology**: Docker containers with `gVisor` (`runsc`) or lightweight microVMs (Firecracker).
- **CPU Quota**: Max 2.0 vCPUs per sandbox (`--cpus=2.0`).
- **Memory Limit**: Max 2048 MB RAM + 512 MB swap (`--memory=2048m --memory-swap=2560m`).
- **Disk Storage**: Max 4 GB ephemeral overlay / tmpfs mounted with `noexec` on `/tmp`.
- **Process Limit**: Max 128 concurrent processes (`--pids-limit=128`) to prevent fork bombs.
- **Execution Timeout**: Hard wall-clock limit of 120 seconds per command execution.

### Secret Stripping & Access Containment:
1. Host `.env`, API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `SECRET_KEY`), and database credentials are **never injected** into sandbox container environments.
2. The Docker daemon socket (`/var/run/docker.sock`) is strictly inaccessible from inside the sandbox.
3. Sandboxes are mounted with read-only root filesystems; only `/workspace` is writable.

---

## 10. Structured Patch Model

Rather than allowing the LLM to output arbitrary, unconstrained file overwrites, all modifications use a **Structured Patch Representation**:

```json
{
  "patch_id": "patch-9a8b7c6d-5e4f",
  "file_path": "backend/app/services/auth_service.py",
  "operation": "modify",
  "old_content_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "new_content_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
  "hunks": [
    {
      "start_line_old": 45,
      "line_count_old": 6,
      "start_line_new": 45,
      "line_count_new": 8,
      "lines": [
        " def validate_session(session_id: str) -> bool:",
        "-    return session_id in active_sessions",
        "+    if not session_id:",
        "+        return False",
        "+    return session_id in active_sessions and not is_expired(session_id)"
      ]
    }
  ],
  "explanation": "Added null check and expiration validation to prevent stale session reuse."
}
```

### Why Structured Patches are Superior to Raw File Overwrites:
1. **Pre-condition Validation**: `old_content_hash` ensures the file hasn't drifted since the agent last inspected it.
2. **Minimal Blast Radius**: Only modified lines are touched; unchanged lines, comments, and formatting in large files remain intact.
3. **Deterministic Reversibility**: Any patch can be cleanly inverted to produce an exact, atomic rollback.
4. **Direct Diff Rendering**: Structured hunks map directly to Monaco Editor diff viewers for user review.

---

## 11. Command & Test Execution Model

Execution tools (`run_tests`, `run_linter`, `run_build`) must execute under strict allowlists derived from repository metadata.

```text
Agent Requests: run_tests(target="backend/tests/unit/test_auth.py")
       ↓
Tool Validator (ToolUsageGuard)
       ├── Check 1: Is command in Project Allowlist? (e.g. pytest, npm test, cargo test, ruff)
       ├── Check 2: Are arguments sanitized? (Reject ;, &&, ||, `, $, |, redirects)
       ├── Check 3: Is target path within repository bounds?
       ↓ (Validated)
Sandbox Runner (executes command with timeout=120s)
       ↓
Output Sanitizer
       ├── Strip ANSI escape codes
       ├── Truncate stdout/stderr (max 100 KB / 500 lines)
       ├── Parse structured test summary (passed, failed, errors)
       └── Redact potential leaked tokens/secrets
       ↓
Return ToolMessage to Agent
```

### Command Allowlist Configuration:
Commands are declared per project type in a declarative manifest (e.g. `.forge/config.yaml` or project settings):
```yaml
testing:
  test_command: "pytest {target} -v --tb=short"
  lint_command: "ruff check {target}"
  build_command: "npm run build"
```

---

## 12. Network Security Model

Code execution sandboxes default to **NO NETWORK ACCESS** (`--network=none`).

### Security Rationale:
1. **Malware Prevention**: Prevents untrusted scripts or compromised dependencies from downloading remote exploits.
2. **Data Exfiltration Defense**: Ensures repository source code and intellectual property cannot be transmitted to external servers.
3. **Internal Network Protection**: Prevents sandboxes from scanning the Forge AI internal VPC, Redis ports (6379), PostgreSQL ports (5432), or cloud metadata endpoints (`169.254.169.254`).

### Controlled Dependency Installation:
If dependency installation is strictly required, it is handled during the **PREPARED** phase via a dedicated package-caching proxy with explicit domain allowlists (e.g. `pypi.org`, `registry.npmjs.org`), followed by immediate network severance before test execution begins.

---

## 13. Git & Branching Strategy

The agent must **never** commit directly to protected branches (`main`, `master`, `production`).

### Branching Standard:
- Working branches follow predictable naming conventions:
  - `forge/{session-id}` (e.g. `forge/sess-a1b2c3d4`)
  - `forge/issue-{issue-id}-{slug}` (e.g. `forge/issue-102-session-validation`)
- Commits generated by Forge AI are authored with standardized metadata:
  ```text
  fix(auth): add expiration check to validate_session

  Resolves session timeout vulnerability by validating timestamps.
  Generated by Forge AI (Session: sess-a1b2c3d4)
  Reviewed-by: user@example.com
  ```

---

## 14. GitHub Integration & Pull Request Lifecycle

Forge AI leverages the GitHub App architecture established in Phase 2 (ADR-012) while expanding capabilities safely:

```text
Agent Session
     ↓
Generate Patch + Test Verification
     ↓
User Clicks [Approve & Create PR]
     ↓
Backend GitHub Service (Server-Side)
     ├── 1. Generate short-lived Installation Access Token (scoped strictly to repository)
     ├── 2. Push branch `forge/issue-102-fix` to origin
     ├── 3. Call GitHub API: POST /repos/{owner}/{repo}/pulls
     │      ├── title: "fix(auth): add expiration check to validate_session"
     │      ├── head: "forge/issue-102-fix"
     │      ├── base: "main"
     │      └── body: Markdown PR description + Forge AI Verification Report
     └── 4. Discard Installation Access Token
     ↓
Return PR URL (e.g. https://github.com/org/repo/pull/42) to User
```

> [!IMPORTANT]
> **Token Isolation Guarantee**: GitHub tokens live exclusively within the backend `GitHubClient` service. **Zero tokens** are passed into the LLM prompt context or sandbox environment.

---

## 15. Diff Review & Rollback Semantics

The user interface will provide a first-class diff review workspace:

```text
┌────────────────────────────────────────────────────────────────────────┐
│  DIFF REVIEW: forge/issue-102-session-validation                        │
├────────────────────────────────────────────────────────────────────────┤
│  Files Changed: 2    Additions: +18    Deletions: -4                   │
│                                                                        │
│  [x] backend/app/services/auth_service.py (+14, -3) [View Diff]        │
│  [x] backend/tests/unit/test_auth.py       (+4,  -1) [View Diff]        │
│                                                                        │
│  VERIFICATION SUITE:                                                   │
│  ✅ Pytest: 149 passed in 1.2s                                         │
│  ✅ Ruff: 0 errors                                                     │
│  ✅ Mypy: Success (82 files checked)                                  │
│                                                                        │
│  [ Approve & Open PR ]      [ Request Revisions ]      [ Discard / Revert ]
└────────────────────────────────────────────────────────────────────────┘
```

### Rollback Guarantee:
If tests fail during iteration or if the user clicks `Discard / Revert`, the system executes an atomic rollback:
1. `git checkout -- .` and `git clean -fd` inside the isolated worktree.
2. In-memory `AgentState["proposed_changes"]` is cleared.
3. The workspace is restored to the exact base commit SHA without leaving untracked artifacts.

---

## 16. Agent State Extension

The transient `AgentState` in LangGraph and the persistent database models are extended to support the modification lifecycle:

### Transient `AgentState` (In-Memory Graph State):
```python
class AgentState(TypedDict, total=False):
    # Existing Phase 4 Fields
    user_query: str
    messages: Annotated[list[BaseMessage], add_messages]
    project_id: str | None
    repository_id: str | None
    branch_id: str | None
    user_id: str | None
    retrieved_context: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    final_answer: str | None
    iteration_count: int
    metadata: dict[str, Any]

    # Future Phase 5 State Extensions
    workspace_id: str | None
    implementation_plan: dict[str, Any] | None
    proposed_patches: list[dict[str, Any]]
    active_patch_id: str | None
    test_run_results: list[dict[str, Any]]
    diff_summary: dict[str, Any] | None
    approval_status: Literal[
        "none", "pending", "approved", "rejected", "changes_requested"
    ]
    lifecycle_state: str
```

### Persistent Database Models (PostgreSQL):
- **`AgentWorkspace`**: `id`, `session_id`, `user_id`, `project_id`, `repository_id`, `worktree_path`, `status`, `created_at`, `expires_at`.
- **`AgentPatch`**: `id`, `workspace_id`, `file_path`, `operation`, `old_content_hash`, `new_content_hash`, `diff`, `status`, `created_at`.
- **`AgentTestExecution`**: `id`, `workspace_id`, `command`, `exit_code`, `stdout_truncated`, `stderr_truncated`, `duration_ms`, `passed_count`, `failed_count`, `created_at`.
- **`AgentApproval`**: `id`, `session_id`, `user_id`, `action_type`, `payload_hash`, `status` (`PENDING`, `APPROVED`, `REJECTED`), `decided_at`.

---

## 17. Extended Agent State Machine

```text
                ┌───────────────┐
                │     IDLE      │
                └───────┬───────┘
                        │ (User Query)
                        ▼
                ┌───────────────┐
                │ INVESTIGATING │ ◄── (Read Tools: search_repository, get_file)
                └───────┬───────┘
                        │ (Code context gathered)
                        ▼
                ┌───────────────┐
                │   PLANNING    │ ──► Generate Implementation Plan
                └───────┬───────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │      AWAITING_APPROVAL       │ ◄── (Gate 1: Approve Plan & Workspace)
         └──────┬───────────────┬───────┘
                │ (Approved)    │ (Rejected)
                ▼               ▼
        ┌───────────────┐  ┌─────────────┐
        │   APPLYING    │  │  CANCELLED  │
        └───────┬───────┘  └─────────────┘
                │ (Patch applied in sandbox)
                ▼
        ┌───────────────┐
        │    TESTING    │ ──► Run tests / linters in sandbox
        └───────┬───────┘
                │
         (Tests Failed) ──► (Loop back to INVESTIGATING / APPLYING to fix)
                │ (Tests Passed)
                ▼
        ┌───────────────┐
        │  DIFF_REVIEW  │ ◄── (Gate 2: Final Human Diff Approval)
        └───────┬───────┘
                │ (Approved)
                ▼
        ┌───────────────┐
        │   COMMITTED   │ ──► Push branch & create GitHub PR
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   COMPLETED   │ ──► Destroy Workspace & Sandbox
        └───────────────┘
```

---

## 18. Observability & Telemetry

Phase 5 introduces granular telemetry across all tool executions, sandbox commands, and approval milestones:

### Structured Telemetry Events:
1. `agent.workspace.created`: Emitted when an ephemeral workspace and worktree are provisioned.
2. `agent.patch.proposed`: Emitted with file paths, diff statistics, and explanation.
3. `agent.patch.applied`: Emitted when atomic hunks are committed to the local sandbox worktree.
4. `agent.test.started` & `agent.test.completed`: Emitted with command name, exit code, and test breakdown.
5. `agent.approval.requested` & `agent.approval.decided`: Emitted with user ID, approval ID, action type, and decision latency.
6. `agent.pr.created`: Emitted with branch name, PR number, and target repository.

### Redaction Standard:
- Telemetry streams pass through `sanitize_secret_text()` to strip API keys, Bearer tokens, and sensitive env variables.
- Large diffs and test logs are capped at 50 KB per event to preserve bandwidth.

---

## 19. Cost Control & Tiered Model Routing

Software engineering workflows involve distinct cognitive tasks. Phase 5 designs a **Tiered Model Routing Policy**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        TIERED MODEL ROUTING POLICY                     │
├──────────────────────┬──────────────────────────┬──────────────────────┤
│ Task Type            │ Recommended Model Tier   │ Examples             │
├──────────────────────┼──────────────────────────┼──────────────────────┤
│ Initial Search & AST │ Fast / Low-Cost Tier     │ Groq Llama 3.1 8B,   │
│ Code Slicing         │                          │ Gemini 1.5 Flash     │
├──────────────────────┼──────────────────────────┼──────────────────────┤
│ Complex Planning &   │ High-Reasoning Tier      │ Groq GPT-OSS 120B,   │
│ Multi-File Strategy  │                          │ Gemini 3.1 Pro,      │
│                      │                          │ OpenAI o3-mini       │
├──────────────────────┼──────────────────────────┼──────────────────────┤
│ Patch Generation &   │ Precision Code Tier      │ OpenAI GPT-4o,       │
│ Syntax Synthesis     │                          │ Claude 3.5 Sonnet    │
├──────────────────────┼──────────────────────────┼──────────────────────┤
│ Final Code Review &  │ Auditor Reasoning Tier   │ Gemini 3.1 Pro,      │
│ Risk Assessment      │                          │ GPT-4o               │
└──────────────────────┴──────────────────────────┴──────────────────────┘
```

---

## 20. Failure Recovery & Error Matrix

| Failure Mode | Root Cause | Recovery Strategy | System State Impact |
|---|---|---|---|
| **Patch Conflict** | Target file drifted from `old_content_hash` | Re-read file, re-compute AST diff, retry patch | Workspace remains clean; no dirty hunks applied |
| **Sandbox Command Timeout** | Test suite hung or entered infinite loop | Hard `SIGKILL` after 120s; return timeout error in `ToolMessage` | Agent is prompted to add timeout or run targeted subtests |
| **Sandbox Crash / OOM** | Memory exceeded 2048 MB limit | Catch OOM exit code (137); emit `agent.error`; destroy container | Safe containment; host backend unaffected |
| **Syntax / Test Regression** | Agent patch broke existing unit tests | Agent receives failure traceback in `ToolMessage` to iterate | Worktree stays in `TESTING` until fixed or reverted |
| **User Rejection** | User rejects proposed diff at Review Gate | Execute atomic rollback (`git checkout -- .`); transition to `CANCELLED` | Workspace cleanly destroyed; zero remote branches created |
| **GitHub API Rate Limit / 429** | Burst PR / branch creation API calls | 429 exponential backoff with `Retry-After` header extraction | Retries up to 3 times before failing safely |
| **Orphaned Sandbox** | User closes browser during active session | Background worker reaper task purges workspaces older than TTL (60m) | Ephemeral disk and container resources reclaimed |

---

## 21. Multi-Tenant Security & Workspace Containment

Phase 5 enforces strict multi-tenant boundary checks before any workspace or tool operation:
1. **Cryptographic Tenant Isolation**: Every workspace is tagged with `organization_id`, `project_id`, and `user_id`. Access requires active JWT verification against organization membership.
2. **Path Containment**: Worktree paths are generated using random UUIDs inside a dedicated runtime root (`/tmp/forge_workspaces/{workspace_id}`). Symlinks pointing outside the workspace directory are rejected.
3. **No Cross-Tenant Shared Mounts**: Each sandbox container receives its own isolated filesystem volume; no volume sharing across workspaces.

---

## 22. Technical Debt Review & Dependencies

Phase 5 design evaluates existing technical debt:

| Debt Item | Priority | Phase 5 Dependency | Strategy |
|---|---|---|---|
| **Token-Level Streaming** | P1 | Low | Current turn-level SSE streaming is fully sufficient for tool execution and approval events; token-level streaming remains a UX enhancement. |
| **Persistent Conversation History** | P2 | Medium | Phase 5 relies on `AgentSession` records; full multi-turn conversation persistence across browser reloads will be formalized in Phase 5B persistence models. |
| **Incremental Row-Copy Optimization** | P2 | Low | Read indexing optimization does not block workspace sandboxing or patch generation. |

---

## 23. Migration Strategy: Phase 4 to Phase 5B

The transition to active code writing will follow a 3-stage safe rollout:
- **Phase 5A (Current)**: Architecture, safety specifications, and ADR approval. Zero code modifications.
- **Phase 5B.1 (Read-Only Planning)**: Enable `propose_patch` and visual diff preview in UI with mock execution.
- **Phase 5B.2 (Sandbox Execution)**: Enable ephemeral Docker sandboxes and `run_tests` behind user opt-in flags.
- **Phase 5B.3 (Full Git/PR Integration)**: Enable branch pushes and PR creation gated by authenticated Human Approval.

---

## 24. Open Questions & Future Considerations

1. **Self-Hosted vs. Cloud MicroVMs**: For enterprise on-premise deployments, should Firecracker microVMs be preferred over Docker/gVisor for strict hypervisor-level isolation?
2. **Language Runtime Pre-warming**: To minimize sandbox startup latency, should pre-warmed container pools with popular runtimes (Python 3.12, Node.js 20, Rust) be maintained in Redis?
3. **Interactive Debugging Sessions**: Should users be allowed to attach a terminal session directly to the sandbox container if the agent struggles with a complex test failure?
