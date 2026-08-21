# Phase 5B: Planning Agent & Ephemeral Workspace Foundation

## 1. Executive Summary

Forge AI Phase 5B establishes the controlled, safety-bounded planning and workspace foundation for the Software Engineering Agent. Phase 5B introduces structured, non-executable implementation planning grounded in repository intelligence, Human-in-the-Loop (HITL) Gate 1 approval contracts, and isolated ephemeral workspaces with deterministic base commit tracking and TTL enforcement.

**Phase 5B Scope Boundary**:
- **Included**: Investigation, Evidence Grounding, `ImplementationPlan` synthesis, Server-side Plan Validation, Human Gate 1 Approval (`AgentApproval`), `AgentWorkspace` database model & filesystem provisioning, Base Commit recording, 60-minute TTL expiration, and Idempotent Cleanup.
- **Excluded**: Code mutation (`apply_patch`), test execution, shell/command execution, Docker/gVisor containers, Git push/commit, and GitHub Pull Request creation.

---

## 2. Planning Agent & Plan Lifecycle

### 2.1 Lifecycle Flow
```
User Feature / Bug Request
            ↓
Repository Investigation (search_repository, search_symbol, get_file)
            ↓
Retrieved Evidence Gathering
            ↓
Plan Synthesis (ImplementationPlan JSON)
            ↓
Server-Side Plan Validation (Paths, File Limits, Grounding)
            ↓
Gate 1 Approval Creation (AgentApproval: status=PENDING)
            ↓
Human Review: [Approve Plan] / [Reject]
            ↓
Explicit Human Approval (status=APPROVED)
            ↓
AgentWorkspace Provisioned (status=PREPARED)
```

### 2.2 Schema Definition: `ImplementationPlan`
```python
class ImplementationPlan(BaseModel):
    id: uuid.UUID
    summary: str
    problem_statement: str
    approach: str
    affected_files: list[AffectedFile]
    new_files: list[str]
    deleted_files: list[str]
    symbols: list[str]
    test_strategy: str
    risks: list[str]
    evidence: list[AgentSourceReference]
    created_at: datetime.datetime
```

### 2.3 Evidence Grounding & Validation
The server strictly validates every generated plan against:
1. **Path Safety**: Rejection of relative parent directory traversals (`../`), Windows drive letters (`C:`), UNC paths, and null bytes (`\x00`).
2. **Duplicate Paths**: Duplicate entries within `affected_files` are rejected.
3. **Change Type Enforcement**: Permitted values: `CREATE`, `MODIFY`, `DELETE`, `UNKNOWN`.
4. **Limits**: Maximum 20 affected files per plan; string fields clamped to 10,000 characters.
5. **Grounding**: For existing files marked `MODIFY` or `DELETE`, validation verifies that the file is anchored to retrieved repository citations or active repository trees.

---

## 3. Human Approval Gate 1 (`PLAN_APPROVAL`)

No workspace can be provisioned and no state mutation can occur without an explicit, authenticated human approval action.

### 3.1 Security & Authorization Contract
- **Explicit Action**: Approval is NEVER inferred from chat messages, viewing the plan, or continuing a conversation. It requires an explicit HTTP `POST /api/v1/agent/approvals/{id}/approve`.
- **Tenant & User Binding**: Approvals are cryptographically tied to `user_id`, `session_id`, `project_id`, and `repository_id`. A user cannot approve another user's plan (returns `403 Forbidden`).
- **Conflict Prevention**: Re-approving an already approved or rejected plan returns `409 Conflict`.

---

## 4. Ephemeral Workspace Model (`AgentWorkspace`)

### 4.1 Model & Lifecycle
`AgentWorkspace` represents an isolated filesystem directory provisioned exclusively for an approved agent session.

```
CREATED -> PREPARED -> ACTIVE -> EXPIRED / DESTROYED / FAILED
```

- **Path Isolation**: Workspaces reside in dedicated root storage (`/tmp/forge_workspaces/{workspace_id}` or OS-specific equivalent) outside the primary repository directory.
- **Base Commit Tracking**: Records `base_commit_sha` matching the active index version or target branch head commit. This serves as the immutable drift-detection foundation for future patch operations.
- **TTL Expiration**: Workspaces have an explicit 60-minute lifetime (`expires_at = created_at + 60m`). Attempts to access an expired workspace return `410 Gone`.
- **Idempotent Cleanup**: `DELETE /api/v1/agent/workspaces/{workspace_id}` removes temporary filesystem directories and transitions the record to `DESTROYED`. Repeated delete calls return status `DESTROYED` without errors.
- **Concurrency Protection**: Rejects duplicate active workspaces for the same session and branch (`409 Conflict`).

---

## 5. API Endpoints Reference

| Method | Path | Description | Response Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/agent/plan` | Investigate and synthesize `ImplementationPlan` | `200 OK` |
| `POST` | `/api/v1/agent/plan/stream` | Stream investigation events and yield plan via SSE | `200 OK (SSE)` |
| `GET` | `/api/v1/agent/approvals/{id}` | Fetch approval gate status and plan payload | `200 OK` |
| `POST` | `/api/v1/agent/approvals/{id}/approve` | Explicitly approve pending plan gate | `200 OK` |
| `POST` | `/api/v1/agent/approvals/{id}/reject` | Explicitly reject pending plan gate | `200 OK` |
| `POST` | `/api/v1/agent/workspaces` | Provision isolated workspace for approved plan | `201 Created` |
| `GET` | `/api/v1/agent/workspaces/{id}` | Retrieve workspace status and metadata | `200 OK / 410 Gone` |
| `DELETE` | `/api/v1/agent/workspaces/{id}` | Idempotently clean up and destroy workspace | `200 OK` |

---

## 6. Server-Sent Events (SSE) Protocol

| Event Name | Payload Highlights |
| :--- | :--- |
| `session.created` | `session_id`, `project_id`, `repository_id`, `branch_id` |
| `agent.started` | `session_id`, `iteration`, `phase` |
| `agent.tool_call` | `tool`, `call_id`, `iteration`, `args` |
| `agent.tool_result` | `tool`, `status`, `duration_ms`, `error` |
| `agent.plan.created` | `plan`, `approval_id`, `approval_status`, `session_id` |
| `agent.approval.required` | `approval_id`, `approval_type`, `session_id`, `status` |
| `agent.error` | `error`, `status_code` |

---

## 7. Frontend User Experience

- **Plan Review Card (`AgentPlanView`)**: Displays structured Summary, Problem Statement, Technical Approach, Affected Files with change-type badges, Test Strategy, Risks, and Citations.
- **Gate 1 Review Actions**: `[Approve Plan]` and `[Reject]` action buttons.
- **Safety Indicator**: Displays `"Isolated Workspace Ready - No code modifications have occurred."` upon successful approval.
- **Strict Boundary**: Zero editable code editors, zero terminal/shell interfaces, and zero direct "Apply Changes" triggers.
