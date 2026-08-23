# Phase 6C: Multi-Agent UI & Developer Experience Specification

**Status:** Complete & Verified  
**Version:** Forge AI v0.6.0  
**Baseline Verified:** 263/263 Backend Tests | 40/40 Frontend Tests | Clean Lint & Types  

---

## 1. Overview & Architecture

Phase 6C provides the user interface and developer experience for Forge AI's centralized multi-agent architecture. It introduces real-time visual tracking of the four specialized engineering roles (**Planner**, **Coder**, **Tester**, and **Reviewer**) governed by the authoritative **Engineering Orchestrator**.

The frontend maintains strict safety invariants:
- **Zero Autonomous Execution**: All 5 human approval gates (`PLAN`, `DIFF`, `COMMIT`, `PUSH`, `PR_CREATE`) remain server-authoritative.
- **Zero Credential Exposure**: Zero API keys, GitHub tokens, database passwords, or JWT secrets are rendered or stored in frontend state.
- **Zero Chain-of-Thought Scratchpad Dumps**: The UI presents structured metadata, unified diffs, test summaries, and security findings without raw internal reasoning traces.

---

## 2. Component Hierarchy

```
AgentChat
└── AgentMessageList
    └── AgentMessage
        ├── AgentTaskHeader (Task title, lifecycle badge, budget meter)
        ├── AgentWorkflowTimeline (4-stage pipeline: Planner -> Coder -> Tester -> Reviewer)
        ├── AgentRoleCard (Expandable inspection for selected active role)
        ├── AgentActivity (Tool activity badges)
        ├── AgentPlanView (Phase 5B Plan & Gate 1 Human Approval)
        ├── AgentDiffView (Phase 5C Patch Preview & Gate 2 Human Approval)
        ├── AgentTestPanel (Phase 5C Sandboxed Test Execution)
        ├── AgentReviewFindings (Phase 6C Reviewer Security & Quality Audit)
        │   └── AgentReviewFindingCard (Severity badge, code evidence, recommendation)
        ├── AgentGitPanel (Phase 5D Git Commit & PR creation with Gates 3, 4, 5)
        └── AgentSources (AST-grounded citations)
```

---

## 3. Component Details

### 3.1 `AgentTaskHeader`
Displays global task metadata:
- **Title**: User prompt or short task summary.
- **Lifecycle Badge**: Semantic colored status (`TASK_CREATED`, `PLAN_READY`, `PATCH_READY`, `TEST_PASSED`, `REVIEW_PASSED`, `COMPLETED`, `WAITING_HUMAN_INTERVENTION`, etc.).
- **Active Agent**: Currently executing agent role (`PLANNER`, `CODER`, `TESTER`, `REVIEWER`, `SUPERVISOR`).
- **Iteration Budget Meter**: Visual progress bar tracking consumption against the 15-iteration limit.

### 3.2 `AgentWorkflowTimeline`
Displays the linear 4-stage multi-agent pipeline:
1. **Planner**: Repository AST investigation and strategy synthesis.
2. **Coder**: Workspace patch generation and defect remediation.
3. **Tester**: Sandboxed execution in gVisor container (`pytest`, `npm test`).
4. **Reviewer**: Adversarial static security and regression audit.

Each stage renders standard role statuses:
- `PENDING`: Gray clock indicator.
- `RUNNING`: Cyan animated spinner with duration counter.
- `COMPLETED`: Emerald checkmark with elapsed seconds.
- `FAILED`: Rose alert circle.
- `WAITING_APPROVAL`: Amber pulsating badge indicating a human approval barrier.
- `SKIPPED`: Slate minus indicator.

### 3.3 `AgentRoleCard`
Expandable role detail card providing role-specific metadata:
- **Planner**: Number of affected files, test strategy, target file paths.
- **Coder**: Number of patch files, patch status, patch operations.
- **Tester**: Test runner binary, exit code, execution duration, and stdout snippet.
- **Reviewer**: Finding counts by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), review decision (`APPROVED` or `CHANGES_REQUESTED`).

### 3.4 `AgentReviewFindings` & `AgentReviewFindingCard`
Interactive defect and security review panel:
- **Severity Summary**: Real-time counter for Critical, High, Medium, Low, and Info findings.
- **Filter Tabs**: Instant filtering by severity level.
- **Group by File**: Hierarchical grouping of findings by repository file path.
- **Finding Details**:
  - Semantic severity badge (accessible icon + text).
  - Target file and line range (`app/api/auth.py:L42-45`).
  - Clear defect description.
  - Code evidence snippet.
  - Actionable remediation guidance.

---

## 4. SSE Stream Event Contracts

The frontend incrementally processes Server-Sent Events from the existing streaming endpoint:

| SSE Event Name | Payload Structure | Frontend State Effect |
| :--- | :--- | :--- |
| `agent.task.created` | `{ task: AgentTask }` | Sets `msg.task` and initial supervisor state |
| `agent.planner.started` | `{ role: "PLANNER" }` | Sets Planner status to `RUNNING` |
| `agent.planner.completed` | `{ plan: ImplementationPlan, duration_ms: number }` | Sets Planner status to `COMPLETED`, stores plan |
| `agent.coder.started` | `{ repair_cycle?: number }` | Sets Coder status to `RUNNING` |
| `agent.coder.completed` | `{ patch: AgentPatch, duration_ms: number }` | Sets Coder status to `COMPLETED`, stores patch |
| `agent.tester.started` | `{ test_command: TestCommand }` | Sets Tester status to `RUNNING` |
| `agent.tester.completed` | `{ status: "PASSED" \| "FAILED", exit_code: number }` | Sets Tester status to `COMPLETED`/`FAILED` |
| `agent.reviewer.started` | `{ role: "REVIEWER" }` | Sets Reviewer status to `RUNNING` |
| `agent.reviewer.completed` | `{ review: AgentReview, duration_ms: number }` | Sets Reviewer status to `COMPLETED`/`FAILED`, stores review |
| `agent.handoff.created` | `{ source_agent: string, target_agent: string }` | Updates `currentAgent` badge |
| `agent.workflow.completed` | `{ status: "completed" }` | Transitions task lifecycle to `COMPLETED` |
| `agent.workflow.failed` | `{ error: string }` | Transitions task lifecycle to `FAILED` |

---

## 5. Responsive Design & Accessibility

- **Responsive Grid**:
  - **Desktop ($\ge$ 1024px)**: 4-column timeline with inline metrics and side-by-side review panels.
  - **Tablet & Mobile ($<$ 1024px)**: Vertically stacked cards with full touch targets and collapsible details.
- **Accessibility Standards**:
  - ARIA tablists and roles on severity filter bars.
  - Explicit `aria-label` attributes on status indicators and collapsible toggles.
  - Multi-attribute indicators: Severity and status are communicated via color, icon, and text labels (never color alone).
