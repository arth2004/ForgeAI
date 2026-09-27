import { useState, useCallback, useRef } from "react";
import { ChatMessage, AgentStreamEvent, AgentSource, AgentToolActivity } from "@/types";
import { streamAgentMessage, sendAgentMessage, formatAgentErrorMessage } from "@/lib/agent-api";

interface UseAgentChatProps {
  projectId: string;
  repositoryId?: string | null;
  branchId?: string | null;
}

export function useAgentChat({ projectId, repositoryId, branchId }: UseAgentChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
      setIsLoading(false);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.status === "streaming" || msg.status === "sending"
            ? { ...msg, status: "completed" }
            : msg
        )
      );
    }
  }, []);

  const clearMessages = useCallback(() => {
    cancelStream();
    setMessages([]);
    setSessionId(null);
    setError(null);
  }, [cancelStream]);

  const sendMessage = useCallback(
    async (text: string, useStreaming: boolean = true) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming || isLoading) return;

      setError(null);
      const userMsgId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const assistantMsgId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

      const userMessage: ChatMessage = {
        id: userMsgId,
        role: "user",
        content: trimmed,
        status: "completed",
        timestamp: new Date().toISOString(),
      };

      const assistantMessage: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        status: useStreaming ? "streaming" : "sending",
        toolActivities: [],
        sources: [],
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      const payload = {
        message: trimmed,
        project_id: projectId,
        repository_id: repositoryId || null,
        branch_id: branchId || null,
        session_id: sessionId || null,
      };

      if (!useStreaming) {
        setIsLoading(true);
        try {
          const resp = await sendAgentMessage(payload);
          setSessionId(resp.session_id);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? {
                    ...msg,
                    content: resp.answer,
                    sources: resp.sources,
                    status: "completed",
                  }
                : msg
            )
          );
        } catch (err: any) {
          const errText = err.message || "Failed to communicate with agent.";
          setError(errText);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, status: "error", error: errText }
                : msg
            )
          );
        } finally {
          setIsLoading(false);
        }
        return;
      }

      // Streaming execution
      setIsStreaming(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        await streamAgentMessage(
          payload,
          (evt: AgentStreamEvent) => {
            const { event, data } = evt;

            switch (event) {
              case "session.created":
                if (data.session_id) {
                  setSessionId(data.session_id);
                }
                break;

              case "agent.started":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, status: "streaming" }
                      : msg
                  )
                );
                break;

              case "agent.tool_call": {
                const activity: AgentToolActivity = {
                  id: data.call_id || `tool-${Date.now()}`,
                  tool: data.tool || "tool",
                  status: "running",
                  iteration: data.iteration,
                };
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existing = msg.toolActivities || [];
                    return {
                      ...msg,
                      toolActivities: [...existing, activity],
                    };
                  })
                );
                break;
              }

              case "agent.tool_result": {
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const updatedTools = (msg.toolActivities || []).map((t) => {
                      if (t.tool === data.tool && t.status === "running") {
                        return {
                          ...t,
                          status: data.status === "success" ? "success" : "failed",
                          duration_ms: data.duration_ms,
                          error: data.error,
                        } as AgentToolActivity;
                      }
                      return t;
                    });
                    return {
                      ...msg,
                      toolActivities: updatedTools,
                    };
                  })
                );
                break;
              }

              case "agent.token": {
                const tokenText = typeof data.content === "string" ? data.content : typeof data.token === "string" ? data.token : "";
                if (tokenText) {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMsgId
                        ? {
                            ...msg,
                            content: (msg.content || "") + tokenText,
                            status: "streaming",
                          }
                        : msg
                    )
                  );
                }
                break;
              }

              case "agent.completed":
                if (data.session_id) {
                  setSessionId(data.session_id);
                }
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          content: data.answer || msg.content || "Answer generated.",
                          sources: (data.sources as AgentSource[]) || msg.sources || [],
                          status: "completed",
                        }
                      : msg
                  )
                );
                break;

              case "agent.plan.created":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          plan: data.plan || data,
                          approvalId: data.approval_id || data.approvalId,
                          approvalStatus: "PENDING",
                        }
                      : msg
                  )
                );
                break;

              case "agent.approval.required":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          approvalId: data.approval_id || data.approvalId || msg.approvalId,
                          approvalStatus: data.status || "PENDING",
                        }
                      : msg
                  )
                );
                break;

              case "agent.approval.resolved":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          approvalStatus: data.status || "APPROVED",
                        }
                      : msg
                  )
                );
                break;

              case "agent.workspace.created":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          workspace: data.workspace || data,
                        }
                      : msg
                  )
                );
                break;

              case "agent.patch.proposed":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          patch: data.patch || data,
                        }
                      : msg
                  )
                );
                break;

              case "agent.patch.applied":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId && msg.patch
                      ? {
                          ...msg,
                          patch: {
                            ...msg.patch,
                            status: "APPLIED",
                            applied_at: new Date().toISOString(),
                          },
                        }
                      : msg
                  )
                );
                break;

              case "agent.test.started":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          testExecution: {
                            test_id: data.test_id || `test-${Date.now()}`,
                            workspace_id: data.workspace_id || "",
                            session_id: sessionId || "",
                            test_command: data.test_command || {
                              runner: data.runner || "pytest",
                              arguments: data.arguments || [],
                            },
                            status: "RUNNING",
                            started_at: new Date().toISOString(),
                          },
                        }
                      : msg
                  )
                );
                break;

              case "agent.test.completed":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          testExecution: {
                            ...(msg.testExecution || {
                              test_id: data.test_id || `test-${Date.now()}`,
                              workspace_id: data.workspace_id || "",
                              session_id: sessionId || "",
                              test_command: data.test_command || {
                                runner: data.runner || "pytest",
                                arguments: data.arguments || [],
                              },
                            }),
                            status: data.status || "PASSED",
                            exit_code: data.exit_code,
                            duration_ms: data.duration_ms,
                            stdout: data.stdout,
                            stderr: data.stderr,
                            completed_at: new Date().toISOString(),
                          },
                        }
                      : msg
                  )
                );
                break;

              case "agent.commit.created":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          commit: data.commit || data,
                        }
                      : msg
                  )
                );
                break;

              case "agent.task.created":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          task: data.task || data,
                          currentAgent: data.active_agent || "SUPERVISOR",
                        }
                      : msg
                  )
                );
                break;

              case "agent.planner.started":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "PENDING" },
                      CODER: { role: "CODER", status: "PENDING" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      currentAgent: "PLANNER",
                      workflowRoles: {
                        ...existingRoles,
                        PLANNER: {
                          ...existingRoles.PLANNER,
                          status: "RUNNING",
                          started_at: new Date().toISOString(),
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.planner.completed":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "PENDING" },
                      CODER: { role: "CODER", status: "PENDING" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      plan: data.plan || msg.plan,
                      workflowRoles: {
                        ...existingRoles,
                        PLANNER: {
                          ...existingRoles.PLANNER,
                          status: "COMPLETED",
                          duration_ms: data.duration_ms || existingRoles.PLANNER.duration_ms,
                          completed_at: new Date().toISOString(),
                          summary: data.summary,
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.coder.started":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "PENDING" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      currentAgent: "CODER",
                      workflowRoles: {
                        ...existingRoles,
                        CODER: {
                          ...existingRoles.CODER,
                          status: "RUNNING",
                          repair_cycle: data.repair_cycle,
                          started_at: new Date().toISOString(),
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.coder.completed":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "PENDING" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      patch: data.patch || msg.patch,
                      workflowRoles: {
                        ...existingRoles,
                        CODER: {
                          ...existingRoles.CODER,
                          status: "COMPLETED",
                          duration_ms: data.duration_ms || existingRoles.CODER.duration_ms,
                          completed_at: new Date().toISOString(),
                          summary: data.summary,
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.tester.started":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "COMPLETED" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      currentAgent: "TESTER",
                      workflowRoles: {
                        ...existingRoles,
                        TESTER: {
                          ...existingRoles.TESTER,
                          status: "RUNNING",
                          started_at: new Date().toISOString(),
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.tester.completed":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "COMPLETED" },
                      TESTER: { role: "TESTER", status: "PENDING" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    const isPassed = data.status === "PASSED" || data.exit_code === 0;
                    return {
                      ...msg,
                      testExecution: data.test_execution || msg.testExecution,
                      workflowRoles: {
                        ...existingRoles,
                        TESTER: {
                          ...existingRoles.TESTER,
                          status: isPassed ? "COMPLETED" : "FAILED",
                          duration_ms: data.duration_ms || existingRoles.TESTER.duration_ms,
                          completed_at: new Date().toISOString(),
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.reviewer.started":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "COMPLETED" },
                      TESTER: { role: "TESTER", status: "COMPLETED" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    return {
                      ...msg,
                      currentAgent: "REVIEWER",
                      workflowRoles: {
                        ...existingRoles,
                        REVIEWER: {
                          ...existingRoles.REVIEWER,
                          status: "RUNNING",
                          started_at: new Date().toISOString(),
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.reviewer.completed":
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantMsgId) return msg;
                    const existingRoles = msg.workflowRoles || {
                      PLANNER: { role: "PLANNER", status: "COMPLETED" },
                      CODER: { role: "CODER", status: "COMPLETED" },
                      TESTER: { role: "TESTER", status: "COMPLETED" },
                      REVIEWER: { role: "REVIEWER", status: "PENDING" },
                    };
                    const reviewObj = data.review || data;
                    const isApproved = reviewObj.status === "APPROVED";
                    return {
                      ...msg,
                      review: reviewObj,
                      workflowRoles: {
                        ...existingRoles,
                        REVIEWER: {
                          ...existingRoles.REVIEWER,
                          status: isApproved ? "COMPLETED" : "FAILED",
                          duration_ms: data.duration_ms || existingRoles.REVIEWER.duration_ms,
                          completed_at: new Date().toISOString(),
                          summary: reviewObj.summary,
                        },
                      },
                    };
                  })
                );
                break;

              case "agent.handoff.created":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          currentAgent: data.target_agent || msg.currentAgent,
                        }
                      : msg
                  )
                );
                break;

              case "agent.workflow.completed":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          status: "completed",
                          task: msg.task
                            ? {
                                ...msg.task,
                                lifecycle_state: "COMPLETED",
                                completed_at: new Date().toISOString(),
                              }
                            : msg.task,
                        }
                      : msg
                  )
                );
                break;

              case "agent.workflow.failed":
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          status: "error",
                          error: data.error || "Multi-agent workflow execution failed.",
                          task: msg.task
                            ? {
                                ...msg.task,
                                lifecycle_state: "FAILED",
                                failure_reason: data.error,
                              }
                            : msg.task,
                        }
                      : msg
                  )
                );
                break;


              case "agent.error": {
                const errMsg =
                  formatAgentErrorMessage(data.status_code, data.error) ||
                  data.error ||
                  "An error occurred during agent reasoning.";
                setError(errMsg);
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, status: "error", error: errMsg }
                      : msg
                  )
                );
                break;
              }
            }
          },
          controller.signal
        );
      } catch (err: any) {
        if (err.name === "AbortError") {
          // User initiated cancel
          return;
        }
        const errText = err.message || "Failed to stream agent response.";
        setError(errText);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, status: "error", error: errText }
              : msg
          )
        );
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [projectId, repositoryId, branchId, sessionId, isStreaming, isLoading]
  );

  return {
    messages,
    sessionId,
    isStreaming,
    isLoading,
    error,
    sendMessage,
    cancelStream,
    clearMessages,
  };
}
