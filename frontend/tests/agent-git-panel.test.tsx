import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { AgentGitPanel } from "@/components/agent/AgentGitPanel";
import { AgentWorkspace } from "@/types/agent";

describe("Phase 5D AgentGitPanel Component", () => {
  const sampleWorkspace: AgentWorkspace = {
    workspace_id: "ws-123",
    session_id: "sess-456",
    organization_id: "org-789",
    project_id: "proj-101",
    repository_id: "repo-102",
    user_id: "user-103",
    status: "ACTIVE",
    path: "/tmp/ws",
    base_commit_sha: "abcd1234efgh5678",
    branch_name: "forge/sess-456",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 3600000).toISOString(),
  };

  it("renders AgentGitPanel with initial Gate 3 pending status", () => {
    render(<AgentGitPanel workspace={sampleWorkspace} />);

    expect(screen.getByText("Git & GitHub Integration (Gates 3, 4, 5)")).toBeInTheDocument();
    expect(screen.getByText("forge/sess-456")).toBeInTheDocument();
    expect(screen.getByText("Pending Gate 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve Commit/i })).toBeInTheDocument();
  });

  it("advances through commit and push approvals", async () => {
    const onCommit = vi.fn().mockResolvedValue(undefined);
    const onPush = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentGitPanel
        workspace={sampleWorkspace}
        onCommit={onCommit}
        onPush={onPush}
      />
    );

    // 1. Approve Commit
    const approveCommitBtn = screen.getByRole("button", { name: /Approve Commit/i });
    fireEvent.click(approveCommitBtn);

    const commitBtn = screen.getByRole("button", { name: /Commit Changes/i });
    expect(commitBtn).toBeInTheDocument();

    // 2. Commit Changes
    fireEvent.click(commitBtn);
    await waitFor(() => {
      expect(onCommit).toHaveBeenCalledWith("ws-123");
    });

    // 3. Approve Push appears
    const approvePushBtn = screen.getByRole("button", { name: /Approve Push/i });
    expect(approvePushBtn).toBeInTheDocument();
    fireEvent.click(approvePushBtn);

    const pushBtn = screen.getByRole("button", { name: /Push Branch/i });
    expect(pushBtn).toBeInTheDocument();
    fireEvent.click(pushBtn);

    await waitFor(() => {
      expect(onPush).toHaveBeenCalledWith("ws-123");
    });
  });
});
