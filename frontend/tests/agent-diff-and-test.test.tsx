import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { AgentDiffView } from "@/components/agent/AgentDiffView";
import { AgentTestPanel } from "@/components/agent/AgentTestPanel";
import { AgentPatch, AgentTestExecution } from "@/types/agent";

describe("Phase 5C Frontend Components", () => {
  const samplePatch: AgentPatch = {
    patch_id: "patch-123",
    workspace_id: "ws-456",
    session_id: "sess-789",
    status: "AWAITING_APPROVAL",
    summary: "Fix authentication boolean logic",
    files: [
      {
        file_path: "app/service.py",
        operation: "MODIFY",
        old_content_hash: "abcd",
        new_content_hash: "ef01",
        hunks: [
          {
            id: "h1",
            old_start: 1,
            old_lines: 2,
            new_start: 1,
            new_lines: 2,
            old_content: "def run():\n    return False\n",
            new_content: "def run():\n    return True\n",
          },
        ],
        reason: "Fix return value",
      },
    ],
    diff_content: "--- a/app/service.py\n+++ b/app/service.py\n@@ -1,2 +1,2 @@\n-    return False\n+    return True\n",
    approval_id: "appr-001",
    created_at: new Date().toISOString(),
  };

  it("renders AgentDiffView with diff content, file lists, and Gate 2 approval actions", async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined);
    const onReject = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentDiffView
        patch={samplePatch}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    expect(screen.getByText("Proposed Patch Review (Gate 2)")).toBeInTheDocument();
    expect(screen.getByText("Fix authentication boolean logic")).toBeInTheDocument();
    expect(screen.getByText("app/service.py")).toBeInTheDocument();
    expect(screen.getByText("MODIFY")).toBeInTheDocument();
    expect(screen.getByText("+ return True")).toBeInTheDocument();

    // Click Approve button
    const approveBtn = screen.getByRole("button", { name: /Approve Patch/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(onApprove).toHaveBeenCalledWith("patch-123");
      expect(screen.getByText("APPROVED")).toBeInTheDocument();
    });
  });

  it("renders Apply button when patch is APPROVED and calls onApply", async () => {
    const approvedPatch: AgentPatch = {
      ...samplePatch,
      status: "APPROVED",
    };
    const onApply = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentDiffView
        patch={approvedPatch}
        onApply={onApply}
      />
    );

    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    const applyBtn = screen.getByRole("button", { name: /Apply Patch/i });
    expect(applyBtn).toBeInTheDocument();

    fireEvent.click(applyBtn);
    await waitFor(() => {
      expect(onApply).toHaveBeenCalledWith("patch-123");
      expect(screen.getByText("APPLIED")).toBeInTheDocument();
    });
  });

  it("renders AgentTestPanel with test runner, arguments, exit code, and stdout", () => {
    const sampleExecution: AgentTestExecution = {
      test_id: "test-777",
      workspace_id: "ws-456",
      session_id: "sess-789",
      test_command: {
        runner: "pytest",
        arguments: ["tests/test_service.py", "-v"],
        timeout_seconds: 60,
      },
      status: "PASSED",
      exit_code: 0,
      stdout: "collected 4 items\ntests/test_service.py .... [100%]\n4 passed in 0.25s",
      stderr: "",
      duration_ms: 250,
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    };

    render(<AgentTestPanel testExecution={sampleExecution} />);

    expect(screen.getByText("Sandboxed Test Execution")).toBeInTheDocument();
    expect(screen.getByText("PASSED")).toBeInTheDocument();
    expect(screen.getByText("$ pytest")).toBeInTheDocument();
    expect(screen.getByText("tests/test_service.py -v")).toBeInTheDocument();
    expect(screen.getByText("250 ms")).toBeInTheDocument();
    expect(screen.getByText(/4 passed in 0.25s/)).toBeInTheDocument();
  });
});
