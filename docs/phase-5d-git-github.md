# Forge AI — Phase 5D: Git Branch, Commit & Pull Request Integration

## 1. Overview

Phase 5D delivers controlled, secure Git and GitHub Pull Request integration for Forge AI while enforcing strict human approval gates at every persistent and remote modification step.

```
Approved Implementation Plan (Gate 1)
                  ↓
          Agent Workspace
                  ↓
       Approved Patch (Gate 2)
                  ↓
        Sandboxed Test Runner
                  ↓
     ┌────────────────────────────┐
     │ HUMAN COMMIT APPROVAL (G3) │
     └─────────────┬──────────────┘
                   ↓
      Local Workspace Git Commit
                   ↓
     ┌────────────────────────────┐
     │  HUMAN PUSH APPROVAL (G4)  │
     └─────────────┬──────────────┘
                   ↓
       Push Branch to Remote
                   ↓
     ┌────────────────────────────┐
     │   HUMAN PR APPROVAL (G5)   │
     └─────────────┬──────────────┘
                   ↓
       Create GitHub Pull Request
```

---

## 2. Security Boundaries & Invariants

1. **No Autonomous Remote Mutation**:
   - The LLM can **never** commit, push, or create a PR via tool calls alone.
   - `CommitChangesTool`, `PushBranchTool`, and `CreatePullRequestTool` unconditionally return `APPROVAL_REQUIRED` if invoked by the model.
   - Only authenticated REST calls corresponding to an authoritative `AgentApproval` record in `APPROVED` status can trigger mutation.
2. **Credential Isolation**:
   - Short-lived GitHub App installation tokens are generated and maintained strictly server-side in-memory.
   - All Git subprocess output and logs pass through `scrub_sensitive_tokens()` to redact tokens (`x-access-token:[REDACTED]@...`).
   - Tokens are never exposed to prompts, agent state, tool outputs, sandbox environments, frontend UI, or database records.
3. **Protected Branch Defense & Non-Force Push**:
   - Pushes to protected branches (`main`, `master`, `production`, `staging`, `develop`, `release/*`) are strictly rejected.
   - Force pushing (`--force`, `--force-with-lease`) is prohibited.
4. **Out of Scope (Explicitly Forbidden)**:
   - Branch merging, auto-merging, branch deletion, release publishing, and automated deployments.

---

## 3. Data Models & Database Migration

### Migration `0008_agent_git_integration.py`

- **`agent_commits` Table**:
  - `id: Uuid` (PK)
  - `workspace_id: Uuid` (FK -> `agent_workspaces.id`, ON DELETE CASCADE)
  - `session_id: Uuid` (FK -> `agent_sessions.id`, ON DELETE CASCADE)
  - `user_id: Uuid` (FK -> `users.id`, ON DELETE CASCADE)
  - `branch_name: String(255)`
  - `commit_sha: String(64)`
  - `message: String(1024)`
  - `created_at`, `updated_at`

- **`agent_pull_requests` Table**:
  - `id: Uuid` (PK)
  - `workspace_id: Uuid` (FK -> `agent_workspaces.id`, ON DELETE CASCADE)
  - `session_id: Uuid` (FK -> `agent_sessions.id`, ON DELETE CASCADE)
  - `repository_id: Uuid` (FK -> `repositories.id`, ON DELETE CASCADE)
  - `branch_name: String(255)`
  - `base_branch: String(255)`
  - `commit_sha: String(64)`
  - `github_pr_number: Integer` (nullable)
  - `github_pr_url: String(1024)` (nullable)
  - `title: String(255)`
  - `body: String`
  - `status: String(32)` (`READY`, `CREATED`, `FAILED`, `CLOSED`)
  - `created_at`, `updated_at`

- **Extensions to Existing Tables**:
  - `agent_workspaces`: added `branch_name`, `current_commit_sha`, `remote_branch_name`.
  - `agent_approvals`: added `commit_id`, `pull_request_id`, and `ApprovalType` values `COMMIT`, `PUSH`, `PR_CREATE`.

---

## 4. REST API Reference

| Method | Endpoint | Description | Gate / Auth |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/agent/workspaces/{id}/branch` | Creates sanitized branch in workspace | Workspace Owner |
| `GET` | `/api/v1/agent/workspaces/{id}/git-status` | Inspects workspace git status | Workspace Owner |
| `POST` | `/api/v1/agent/workspaces/{id}/commit` | Commits approved changes | Gate 3 (`COMMIT` approved) |
| `POST` | `/api/v1/agent/workspaces/{id}/push` | Pushes branch to remote repository | Gate 4 (`PUSH` approved) |
| `POST` | `/api/v1/agent/pulls/{id}/create` | Creates GitHub Pull Request | Gate 5 (`PR_CREATE` approved) |
| `GET` | `/api/v1/agent/pulls/{id}` | Retrieves Pull Request details | Session Owner |

---

## 5. Verification Results

- **Backend Pytest Suite**: 229/229 tests passed (0 regressions).
- **Frontend Vitest Suite**: 25/25 tests passed.
- **Ruff Linter**: Clean (0 errors).
- **Mypy Typechecker**: Clean (0 errors across 98 source files).
- **Next.js Production Build**: Compiled successfully.
