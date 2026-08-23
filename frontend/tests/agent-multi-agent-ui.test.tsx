import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { AgentWorkflowTimeline } from "@/components/agent/AgentWorkflowTimeline";
import { AgentRoleCard } from "@/components/agent/AgentRoleCard";
import { AgentReviewFindings } from "@/components/agent/AgentReviewFindings";
import { AgentReviewFindingCard } from "@/components/agent/AgentReviewFindingCard";
import { AgentTaskHeader } from "@/components/agent/AgentTaskHeader";
import { AgentMessage } from "@/components/agent/AgentMessage";
import {
  AgentWorkflowRoles,
  AgentTask,
  AgentReview,
  ReviewFinding,
  ChatMessage,
} from "@/types/agent";

describe("Phase 6C Multi-Agent UI Components", () => {
  const sampleRoles: AgentWorkflowRoles = {
    PLANNER: {
      role: "PLANNER",
      status: "COMPLETED",
      duration_ms: 1200,
      summary: "Explored 4 AST symbols across 2 files.",
    },
    CODER: {
      role: "CODER",
      status: "COMPLETED",
      duration_ms: 2400,
      repair_cycle: 1,
      summary: "Synthesized structured patch proposal.",
    },
    TESTER: {
      role: "TESTER",
      status: "COMPLETED",
      duration_ms: 800,
      summary: "Executed pytest suite with 0 failures.",
    },
    REVIEWER: {
      role: "REVIEWER",
      status: "RUNNING",
      started_at: new Date().toISOString(),
    },
  };

  const sampleTask: AgentTask = {
    id: "task-001-uuid",
    session_id: "sess-001",
    user_id: "user-001",
    organization_id: "org-001",
    project_id: "proj-001",
    repository_id: "repo-001",
    branch_id: "branch-001",
    title: "Fix Authentication Token Expiry Race Condition",
    prompt: "Fix token refresh logic when token expires under concurrency",
    lifecycle_state: "REVIEWING",
    active_agent: "REVIEWER",
    iteration_count: 3,
    tool_call_count: 8,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const sampleFindings: ReviewFinding[] = [
    {
      id: "f-1",
      severity: "CRITICAL",
      category: "SECURITY",
      file_path: "app/api/auth.py",
      start_line: 42,
      end_line: 45,
      description: "SQL injection vulnerability in raw query parameter concatenation.",
      evidence: "query = f'SELECT * FROM users WHERE id = {user_input}'",
      recommendation: "Use parameterized query bindings with SQLAlchemy select() statement.",
    },
    {
      id: "f-2",
      severity: "HIGH",
      category: "CORRECTNESS",
      file_path: "app/services/token.py",
      start_line: 110,
      description: "Missing mutex lock on concurrent refresh token validation.",
      recommendation: "Acquire distributed advisory lock during token refresh.",
    },
    {
      id: "f-3",
      severity: "MEDIUM",
      category: "TEST_COVERAGE",
      file_path: "app/services/token.py",
      description: "Missing test case for invalid signature JWT decoding.",
    },
  ];

  const sampleReview: AgentReview = {
    id: "rev-001",
    task_id: "task-001-uuid",
    patch_id: "patch-001",
    status: "CHANGES_REQUESTED",
    summary: "Found 1 Critical security vulnerability and 1 High defect.",
    findings: sampleFindings,
    created_at: new Date().toISOString(),
  };

  it("1. renders AgentWorkflowTimeline with correct role stages and active agent status", () => {
    const onSelectRole = vi.fn();
    render(
      <AgentWorkflowTimeline
        roles={sampleRoles}
        currentAgent="REVIEWER"
        iterationCount={3}
        maxIterations={15}
        onSelectRole={onSelectRole}
      />
    );

    expect(screen.getByText("Engineering Workflow")).toBeInTheDocument();
    expect(screen.getByText("Active: REVIEWER")).toBeInTheDocument();
    expect(screen.getByText(/Iteration/i)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();


    // Check all 4 roles are rendered
    expect(screen.getByText("Planner")).toBeInTheDocument();
    expect(screen.getByText("Coder")).toBeInTheDocument();
    expect(screen.getByText("Tester")).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();

    // Check completed durations
    expect(screen.getByText("1.2s")).toBeInTheDocument();
    expect(screen.getByText("2.4s")).toBeInTheDocument();
    expect(screen.getByText("0.8s")).toBeInTheDocument();

    // Role selection interaction
    const plannerButton = screen.getByRole("button", { name: /Planner stage/i });
    fireEvent.click(plannerButton);
    expect(onSelectRole).toHaveBeenCalledWith("PLANNER");
  });

  it("2. renders AgentTaskHeader with title, active role, and budget meter", () => {
    render(
      <AgentTaskHeader
        task={sampleTask}
        repositoryName="forge-ai/core-engine"
        branchName="fix-auth-race"
      />
    );

    expect(screen.getByText("Fix Authentication Token Expiry Race Condition")).toBeInTheDocument();
    expect(screen.getByText("REVIEWING")).toBeInTheDocument();
    expect(screen.getByText("forge-ai/core-engine")).toBeInTheDocument();
    expect(screen.getByText("fix-auth-race")).toBeInTheDocument();
    expect(screen.getByText("Task #task-001")).toBeInTheDocument();
    expect(screen.getByText("3/15")).toBeInTheDocument();
  });

  it("3. renders AgentRoleCard for Planner and Reviewer roles", () => {
    const { rerender } = render(
      <AgentRoleCard
        roleState={sampleRoles.PLANNER}
        plan={{
          id: "plan-1",
          summary: "Plan: Refactor JWT Validator",
          problem_statement: "Fix race condition",
          approach: "Introduce locks",
          affected_files: [{ file_path: "app/auth.py", change_type: "MODIFY", reason: "Add lock", symbols: [] }],
          new_files: [],
          deleted_files: [],
          symbols: [],
          test_strategy: "pytest tests/test_auth.py",
          risks: [],
          created_at: new Date().toISOString(),
        }}
      />
    );

    expect(screen.getByText("PLANNER Agent")).toBeInTheDocument();
    expect(screen.getByText("Plan: Refactor JWT Validator")).toBeInTheDocument();
    expect(screen.getByText("1 affected files")).toBeInTheDocument();

    // Re-render as Reviewer card
    rerender(
      <AgentRoleCard
        roleState={sampleRoles.REVIEWER}
        review={sampleReview}
      />
    );

    expect(screen.getByText("REVIEWER Agent")).toBeInTheDocument();
    expect(screen.getByText("CHANGES_REQUESTED")).toBeInTheDocument();
    expect(screen.getByText("3 total findings:")).toBeInTheDocument();
    expect(screen.getByText("1 Critical")).toBeInTheDocument();
    expect(screen.getByText("1 High")).toBeInTheDocument();
  });

  it("4. renders AgentReviewFindings with severity counts, filter tabs, and file grouping", () => {
    render(<AgentReviewFindings review={sampleReview} />);

    expect(screen.getByText("Reviewer Security & Quality Audit")).toBeInTheDocument();
    expect(screen.getByText("CHANGES_REQUESTED")).toBeInTheDocument();
    expect(screen.getByText("All (3)")).toBeInTheDocument();
    expect(screen.getByText("Critical (1)")).toBeInTheDocument();
    expect(screen.getByText("High (1)")).toBeInTheDocument();
    expect(screen.getByText("Medium (1)")).toBeInTheDocument();

    // Verify all 3 finding descriptions are rendered
    expect(screen.getByText(/SQL injection vulnerability/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing mutex lock/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing test case/i)).toBeInTheDocument();

    // Click Critical Filter
    const criticalTab = screen.getByRole("tab", { name: /Critical/i });
    fireEvent.click(criticalTab);

    expect(screen.getByText(/SQL injection vulnerability/i)).toBeInTheDocument();
    expect(screen.queryByText(/Missing mutex lock/i)).not.toBeInTheDocument();

    // Group by File
    const groupByFileBtn = screen.getByRole("button", { name: /Group by File/i });
    fireEvent.click(groupByFileBtn);
    expect(screen.getAllByText("app/api/auth.py").length).toBeGreaterThanOrEqual(1);
  });

  it("5. renders AgentReviewFindingCard with expandable code evidence and recommendation", () => {
    render(<AgentReviewFindingCard finding={sampleFindings[0]} />);

    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("SECURITY")).toBeInTheDocument();
    expect(screen.getByText("app/api/auth.py")).toBeInTheDocument();
    expect(screen.getByText(/L42-45/)).toBeInTheDocument();


    // Click expand button to view evidence & remediation
    const expandBtn = screen.getByRole("button", { name: /Expand finding details/i });
    fireEvent.click(expandBtn);

    expect(screen.getByText("Code Evidence")).toBeInTheDocument();
    expect(screen.getByText(/SELECT \* FROM users WHERE id/i)).toBeInTheDocument();
    expect(screen.getByText("Remediation Guidance")).toBeInTheDocument();
    expect(screen.getByText(/Use parameterized query bindings/i)).toBeInTheDocument();
  });

  it("6. renders clean empty review state when review has 0 findings (APPROVED)", () => {
    const cleanReview: AgentReview = {
      id: "rev-clean",
      task_id: "task-002",
      status: "APPROVED",
      summary: "Clean review passed.",
      findings: [],
      created_at: new Date().toISOString(),
    };

    render(<AgentReviewFindings review={cleanReview} />);

    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    expect(screen.getByText(/Clean review: No critical, security, or regression findings detected/i)).toBeInTheDocument();
  });

  it("7. renders AgentMessage integrated with task header, workflow timeline, and review findings", () => {
    const message: ChatMessage = {
      id: "msg-1",
      role: "assistant",
      content: "I have investigated the codebase and synthesized a structured patch.",
      status: "completed",
      task: sampleTask,
      workflowRoles: sampleRoles,
      review: sampleReview,
      timestamp: new Date().toISOString(),
    };

    render(<AgentMessage message={message} />);

    expect(screen.getByTestId("assistant-message")).toBeInTheDocument();
    expect(screen.getByTestId("agent-task-header")).toBeInTheDocument();
    expect(screen.getByTestId("agent-workflow-timeline")).toBeInTheDocument();
    expect(screen.getByTestId("agent-review-findings-panel")).toBeInTheDocument();
    expect(screen.getByText("I have investigated the codebase and synthesized a structured patch.")).toBeInTheDocument();
  });
});
