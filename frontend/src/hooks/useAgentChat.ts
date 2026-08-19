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

              case "agent.completed":
                if (data.session_id) {
                  setSessionId(data.session_id);
                }
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          content: data.answer || "Answer generated.",
                          sources: (data.sources as AgentSource[]) || [],
                          status: "completed",
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
