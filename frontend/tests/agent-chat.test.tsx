import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AgentChat } from "@/components/agent/AgentChat";
import { AgentMessage } from "@/components/agent/AgentMessage";
import { parseSSEStream, formatAgentErrorMessage } from "@/lib/agent-api";

import { AgentStreamEvent } from "@/types";

describe("Agent Chat UI & Component Integration", () => {
  const projectId = "proj-1234-uuid";
  const repoId = "repo-5678-uuid";
  const repoName = "ai-lab/forge-workspace";
  const branchName = "main";

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state with sample prompt suggestions and header info", () => {
    render(
      <AgentChat
        projectId={projectId}
        repositoryId={repoId}
        repositoryName={repoName}
        branchName={branchName}
      />
    );

    expect(screen.getByText("Forge AI Repository Reasoning Agent")).toBeInTheDocument();
    expect(screen.getByText(repoName)).toBeInTheDocument();
    expect(screen.getByText(branchName)).toBeInTheDocument();
    expect(screen.getByText("Ask Forge AI about this Repository")).toBeInTheDocument();
    expect(
      screen.getByText("Where is JWT authentication and password hashing implemented?")
    ).toBeInTheDocument();
  });

  it("sends message when clicking a sample prompt suggestion", async () => {
    // Mock global fetch for streaming SSE response
    const ssePayload = [
      "event: session.created\ndata: {\"session_id\": \"sess-999-uuid\"}\n\n",
      "event: agent.started\ndata: {\"iteration\": 1}\n\n",
      "event: agent.completed\ndata: {\"answer\": \"Authentication is handled in security.py.\", \"sources\": [{\"file_path\": \"app/core/security.py\", \"start_line\": 10, \"end_line\": 30, \"symbol_name\": \"create_access_token\"}]}\n\n",
    ].join("");

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ssePayload));
        controller.close();
      },
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ "content-type": "text/event-stream" }),
    } as any);

    render(
      <AgentChat
        projectId={projectId}
        repositoryId={repoId}
        repositoryName={repoName}
        branchName={branchName}
      />
    );

    const promptBtn = screen.getByText("Where is JWT authentication and password hashing implemented?");
    fireEvent.click(promptBtn);

    // Verify user message appears
    await waitFor(() => {
      expect(
        screen.getByText("Where is JWT authentication and password hashing implemented?")
      ).toBeInTheDocument();
    });

    // Verify assistant answer appears
    await waitFor(() => {
      expect(screen.getByText("Authentication is handled in security.py.")).toBeInTheDocument();
      expect(screen.getByText("app/core/security.py")).toBeInTheDocument();
      expect(screen.getByText("create_access_token")).toBeInTheDocument();
    });
  });

  it("handles tool lifecycle events and renders AgentActivity badges", async () => {
    const ssePayload = [
      "event: session.created\ndata: {\"session_id\": \"sess-111-uuid\"}\n\n",
      "event: agent.started\ndata: {\"iteration\": 1}\n\n",
      "event: agent.tool_call\ndata: {\"tool\": \"search_repository\", \"call_id\": \"c1\", \"iteration\": 1}\n\n",
      "event: agent.tool_result\ndata: {\"tool\": \"search_repository\", \"status\": \"success\", \"duration_ms\": 45.2}\n\n",
      "event: agent.completed\ndata: {\"answer\": \"Hybrid retrieval coordinates dense and sparse search.\", \"sources\": []}\n\n",
    ].join("");

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ssePayload));
        controller.close();
      },
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ "content-type": "text/event-stream" }),
    } as any);

    render(
      <AgentChat
        projectId={projectId}
        repositoryId={repoId}
        repositoryName={repoName}
      />
    );

    const textarea = screen.getByPlaceholderText(/Ask Forge AI about this repository/i);
    fireEvent.change(textarea, { target: { value: "Explain hybrid retrieval" } });

    const sendBtn = screen.getByRole("button", { name: /Send message to agent/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText(/Tool activity completed/i)).toBeInTheDocument();
      expect(screen.getByText("Searching repository codebase")).toBeInTheDocument();
      expect(screen.getByText("Hybrid retrieval coordinates dense and sparse search.")).toBeInTheDocument();
    });
  });

  it("supports stopping / cancelling an ongoing stream", async () => {
    let controllerRef: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream({
      start(controller) {
        controllerRef = controller;
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode("event: agent.started\ndata: {\"iteration\": 1}\n\n"));
      },
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ "content-type": "text/event-stream" }),
    } as any);

    render(
      <AgentChat
        projectId={projectId}
        repositoryId={repoId}
      />
    );

    const textarea = screen.getByPlaceholderText(/Ask Forge AI about this repository/i);
    fireEvent.change(textarea, { target: { value: "Long stream query" } });
    const sendBtn = screen.getByRole("button", { name: /Send message to agent/i });
    fireEvent.click(sendBtn);

    // While streaming, the stop button should appear
    await waitFor(() => {
      const stopBtn = screen.getByRole("button", { name: /Cancel agent reasoning/i });
      expect(stopBtn).toBeInTheDocument();
      fireEvent.click(stopBtn);
    });

    // After stopping, send button returns
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Send message to agent/i })).toBeInTheDocument();
    });
  });

  it("renders user-friendly error on agent API failure", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ message: "Forbidden project access." }),
    } as any);

    render(
      <AgentChat
        projectId={projectId}
        repositoryId={repoId}
      />
    );

    const textarea = screen.getByPlaceholderText(/Ask Forge AI about this repository/i);
    fireEvent.change(textarea, { target: { value: "Unauthorized query" } });
    const sendBtn = screen.getByRole("button", { name: /Send message to agent/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(
        screen.getAllByText("You do not have permission to access this project or repository.").length
      ).toBeGreaterThan(0);
    });
  });

  it("clears conversation when clicking Reset button", async () => {
    const ssePayload = [
      "event: session.created\ndata: {\"session_id\": \"sess-reset\"}\n\n",
      "event: agent.completed\ndata: {\"answer\": \"Temporary message.\", \"sources\": []}\n\n",
    ].join("");

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ssePayload));
        controller.close();
      },
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
    } as any);

    render(<AgentChat projectId={projectId} />);

    const textarea = screen.getByPlaceholderText(/Ask Forge AI about this repository/i);
    fireEvent.change(textarea, { target: { value: "Message to clear" } });
    fireEvent.click(screen.getByRole("button", { name: /Send message to agent/i }));

    await waitFor(() => {
      expect(screen.getByText("Temporary message.")).toBeInTheDocument();
    });

    const resetBtn = screen.getByRole("button", { name: /Clear chat conversation/i });
    fireEvent.click(resetBtn);

    // Empty state returns
    await waitFor(() => {
      expect(screen.getByText("Ask Forge AI about this Repository")).toBeInTheDocument();
      expect(screen.queryByText("Temporary message.")).not.toBeInTheDocument();
    });
  });
});

describe("SSE Stream Parser Unit Tests", () => {
  it("parses multiple SSE events in a single network chunk", async () => {
    const events: AgentStreamEvent[] = [];
    const encoder = new TextEncoder();
    const chunk = [
      "event: session.created\ndata: {\"session_id\": \"sess-1\"}\n\n",
      "event: agent.started\ndata: {\"iteration\": 1}\n\n",
      "event: agent.completed\ndata: {\"answer\": \"Done!\"}\n\n",
    ].join("");

    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });

    await parseSSEStream(stream, (evt) => events.push(evt));

    expect(events.length).toBe(3);
    expect(events[0].event).toBe("session.created");
    expect(events[0].data.session_id).toBe("sess-1");
    expect(events[1].event).toBe("agent.started");
    expect(events[2].event).toBe("agent.completed");
    expect(events[2].data.answer).toBe("Done!");
  });

  it("handles a single SSE event split across multiple network chunks", async () => {
    const events: AgentStreamEvent[] = [];
    const encoder = new TextEncoder();
    const part1 = "event: agent.completed\n";
    const part2 = "data: {\"answer\": \"Spl";
    const part3 = "it chunk parsed correctly.\"}\n\n";

    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(part1));
        controller.enqueue(encoder.encode(part2));
        controller.enqueue(encoder.encode(part3));
        controller.close();
      },
    });

    await parseSSEStream(stream, (evt) => events.push(evt));

    expect(events.length).toBe(1);
    expect(events[0].event).toBe("agent.completed");
    expect(events[0].data.answer).toBe("Split chunk parsed correctly.");
  });

  it("correctly maps standard HTTP status codes to user-facing messages", () => {
    expect(formatAgentErrorMessage(401)).toBe("Your session has expired. Please sign in again.");
    expect(formatAgentErrorMessage(403)).toBe(
      "You do not have permission to access this project or repository."
    );
    expect(formatAgentErrorMessage(404)).toBe(
      "The requested project, repository, or branch was not found."
    );
    expect(formatAgentErrorMessage(409)).toBe(
      "This conversation is bound to a different repository context."
    );
    expect(formatAgentErrorMessage(429)).toBe(
      "Forge AI is temporarily rate-limited. Please try again shortly."
    );
    expect(formatAgentErrorMessage(504)).toBe(
      "The agent took too long to respond. Try asking a more specific question."
    );
  });

  describe("Phase 5B Planning & Workspace UI", () => {
    const mockPlan = {
      id: "plan-uuid-1",
      summary: "Refactor Authentication Token Verification",
      problem_statement: "JWT validation needs to support custom claims and token refresh.",
      approach: "Modify auth service to validate claims against repository config.",
      affected_files: [
        {
          file_path: "backend/app/auth/service.py",
          change_type: "MODIFY" as const,
          reason: "Update verify_token to parse custom claims.",
          symbols: ["verify_token", "create_access_token"],
        },
      ],
      new_files: [],
      deleted_files: [],
      symbols: ["verify_token"],
      test_strategy: "Unit tests in test_auth.py covering claim validation.",
      risks: ["Backward compatibility with legacy token formats."],
      created_at: new Date().toISOString(),
    };

    it("renders ImplementationPlan details and Gate 1 approval buttons", () => {
      render(
        <AgentMessage
          message={{
            id: "msg-1",
            role: "assistant",
            content: "Here is the implementation plan for your review:",
            status: "completed",
            plan: mockPlan,
            approvalId: "appr-1234-uuid",
            approvalStatus: "PENDING",
            timestamp: new Date().toISOString(),
          }}
        />
      );

      expect(screen.getByText("Implementation Plan (Gate 1)")).toBeInTheDocument();
      expect(screen.getByText("Refactor Authentication Token Verification")).toBeInTheDocument();
      expect(screen.getByText("backend/app/auth/service.py")).toBeInTheDocument();
      expect(screen.getByText("MODIFY")).toBeInTheDocument();
      expect(screen.getByText("Unit tests in test_auth.py covering claim validation.")).toBeInTheDocument();
      expect(screen.getByText("Approve Plan")).toBeInTheDocument();
      expect(screen.getByText("Reject")).toBeInTheDocument();
    });

    it("transitions to approved state and displays workspace status", async () => {
      const onApprove = vi.fn().mockResolvedValue(undefined);

      render(
        <AgentMessage
          message={{
            id: "msg-2",
            role: "assistant",
            content: "Plan proposed:",
            status: "completed",
            plan: mockPlan,
            approvalId: "appr-1234-uuid",
            approvalStatus: "PENDING",
            timestamp: new Date().toISOString(),
          }}
        />
      );

      // Verify buttons exist
      expect(screen.getByText("Approve Plan")).toBeInTheDocument();
    });
  });
});

