# Forge AI — Phase 6B Multi-Agent Engineering Runtime Implementation

## Document Metadata
- **Status:** Implemented & Verified Specification
- **Phase:** Phase 6B (Multi-Agent Engineering Runtime)
- **Target Release:** v0.6.0
- **Author:** Forge AI Engineering Team
- **Date:** August 2026

---

## 1. Runtime Architecture

Phase 6B transitions Forge AI from a single-agent engineering loop into a **Centralized, Deterministic Multi-Agent Engineering System**. The architecture is governed by an authoritative **Engineering Orchestrator** compiled as a LangGraph `StateGraph(MultiAgentState)`.

```
                        ┌──────────────────────────────┐
                        │   Engineering Orchestrator   │
                        │ (LangGraph Supervisor Guard) │
                        └──────────────┬───────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ↓                          ↓                          ↓
     ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
     │Planner Agent │           │ Coder Agent  │           │Reviewer Agent│
     │ (Read-Only)  │           │(Diff Synth)  │           │(Adversarial) │
     └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
            │                          │                          │
            │                          ↓                          │
            │                    Patch System                     │
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ↓
                                ┌──────────────┐
                                │ Tester Agent │
                                │(gVisor Exec) │
                                └──────┬───────┘
                                       │
                                       ↓
                          Verified Engineering Result
```

---

## 2. Specialized Agent Roles & Responsibilities

### 2.1 Planner Agent (`app.agent.multi_agent.planner.PlannerAgent`)
- **Responsibilities:** Investigates repository AST, symbol cross-references, and directory structures. Synthesizes a structured `ImplementationPlan`.
- **Allowed Tools:** `search_repository`, `search_symbol`, `get_file`.
- **Forbidden Actions:** Workspace mutation, patch application, shell execution, git commit/push, pull request creation.

### 2.2 Coder Agent (`app.agent.multi_agent.coder.CoderAgent`)
- **Responsibilities:** Consumes approved implementation plans and synthesizes structured `AgentPatch` objects with hunk offsets and SHA256 pre-hashes. Incorporates feedback from test failures and reviewer findings during repair cycles.
- **Allowed Tools:** `search_repository`, `search_symbol`, `get_file`, `propose_patch`.
- **Forbidden Actions:** Autonomous patch application (`apply_patch`), commit (`git_commit`), push (`git_push`), PR creation (`create_pull_request`).

### 2.3 Tester Agent (`app.agent.multi_agent.tester.TesterAgent`)
- **Responsibilities:** Executes allowlisted test suites (`pytest`, `vitest`, `npm test`) inside non-networked (`--network=none`), CPU/RAM-bounded `gVisor` containers.
- **Allowed Tools:** `run_tests`.
- **Forbidden Actions:** Arbitrary shell command execution (`sh`, `bash`), production filesystem mutation, network egress.

### 2.4 Reviewer Agent (`app.agent.multi_agent.reviewer.ReviewerAgent`)
- **Responsibilities:** Conducts adversarial static security and regression audits of proposed patches. Emits structured `ReviewFinding` entities categorized across `SECURITY`, `REGRESSION`, `CORRECTNESS`, `ARCHITECTURE`, and `STYLE`.
- **Allowed Tools:** `search_repository`, `search_symbol`, `get_file`.
- **Forbidden Actions:** Any workspace or persistent mutation. Output is purely advisory (`APPROVED` or `CHANGES_REQUESTED`).

---

## 3. Multi-Agent State & Persistence Model

### 3.1 `MultiAgentState` (`app.agent.multi_agent.state.MultiAgentState`)
TypedDict state passed between the Orchestrator and specialized subagents:
- `task_id`, `session_id`, `user_id`, `organization_id`, `project_id`, `repository_id`, `workspace_id`
- `active_agent`, `lifecycle_state`
- `implementation_plan`, `investigation_summary`, `affected_files`
- `proposed_patches`, `active_patch_id`, `active_patch`
- `test_results`, `last_test_passed`, `test_repair_count`
- `review_findings`, `review_status`, `review_iteration_count`
- `iteration_count`, `tool_call_count`, `total_tokens_used`
- `approval_status` (Mapping of `PLAN`, `DIFF`, `COMMIT`, `PUSH`, `PR_CREATE`)

### 3.2 Relational Persistence (`0009_agent_task_and_review.py`)
- **`AgentTask`:** Tracks orchestration lifecycle state, active agent, iteration counters, and completion status.
- **`AgentReview`:** Stores code review evaluation reports.
- **`ReviewFinding`:** Stores granular line-level defect, regression, and security findings.

---

## 4. Human Approval Boundaries

Phase 6B preserves all 5 Human Approval Gates established in Phase 5:
1. **Gate 1 (`PLAN`):** Human signs off on architectural approach and affected files before workspace provisioning.
2. **Gate 2 (`DIFF`):** Human signs off on visual diff before atomic application and testing.
3. **Gate 3 (`COMMIT`):** Human authorizes local git commit with author attribution.
4. **Gate 4 (`PUSH`):** Human authorizes pushing branch to remote GitHub repository.
5. **Gate 5 (`PR_CREATE`):** Human authorizes opening the live GitHub Pull Request.

**Inviolable Invariant:** Neither the Orchestrator, Planner, Coder, Tester, nor Reviewer Agent can bypass any approval gate.

---

## 5. Cost & Execution Guardrails

```python
MAX_TOTAL_WORKFLOW_ITERATIONS = 15
MAX_PLANNER_INVESTIGATION_STEPS = 5
MAX_CODER_RETRY_CYCLES = 3
MAX_TEST_REPAIR_LOOPS = 3
MAX_REVIEW_ITERATIONS = 2
MAX_TOTAL_TOOL_CALLS = 30
MAX_TOTAL_LLM_TOKENS = 150000
MAX_WORKFLOW_TIMEOUT_SECONDS = 600
```

---

## 6. Provider Routing & Resilience

Provider routing is strictly **configuration-driven**:
- **Planner:** Configured via `AGENT_PLANNER_PROVIDER` / `AGENT_PLANNER_MODEL`.
- **Coder:** Configured via `AGENT_CODER_PROVIDER` / `AGENT_CODER_MODEL`.
- **Tester:** Configured via `AGENT_TESTER_PROVIDER` / `AGENT_TESTER_MODEL`.
- **Reviewer:** Configured via `AGENT_REVIEWER_PROVIDER` / `AGENT_REVIEWER_MODEL`.

**Resilience Distinction:**
- HTTP 429 rate limit backoff and retry is enabled.
- Automatic, unconfigured provider switching after failures is **disabled** to preserve architectural determinism.

---

## 7. Observability & Telemetry

The runtime emits structured events over Server-Sent Events (SSE):
- `agent.task.created`
- `agent.planner.started` / `agent.planner.completed`
- `agent.coder.started` / `agent.coder.completed`
- `agent.tester.started` / `agent.tester.completed`
- `agent.reviewer.started` / `agent.reviewer.completed`
- `agent.approval.required`
- `agent.workflow.completed` / `agent.workflow.failed`

All event payloads are scrubbed of credentials, API keys, and internal scratchpads.
