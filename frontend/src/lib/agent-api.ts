import { AgentChatRequest, AgentChatResponse, AgentStreamEvent } from "@/types";
import { apiClient } from "@/lib/api-client";

export function formatAgentErrorMessage(status: number, defaultMsg?: string): string {
  switch (status) {
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You do not have permission to access this project or repository.";
    case 404:
      return "The requested project, repository, or branch was not found.";
    case 409:
      return "This conversation is bound to a different repository context.";
    case 422:
      return "Invalid message payload. Please verify your query length.";
    case 429:
      return "Forge AI is temporarily rate-limited. Please try again shortly.";
    case 504:
      return "The agent took too long to respond. Try asking a more specific question.";
    default:
      return defaultMsg || "An unexpected error occurred while communicating with Forge AI.";
  }
}

/**
 * Robust Server-Sent Events (SSE) stream parser capable of handling split chunks,
 * multi-event buffers, and dynamic event types.
 */
export async function parseSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: AgentStreamEvent) => void
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");

      // Keep the last partial event fragment in the buffer
      buffer = parts.pop() || "";

      for (const block of parts) {
        const lines = block.split("\n");
        let currentEvent = "";
        let currentData = "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("event:")) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith("data:")) {
            const dataSlice = trimmed.slice(5).trim();
            currentData = currentData ? currentData + "\n" + dataSlice : dataSlice;
          }
        }

        if (currentEvent && currentData) {
          try {
            const parsedData = JSON.parse(currentData);
            onEvent({
              event: currentEvent as any,
              data: parsedData,
            });
          } catch {
            // Non-JSON or malformed payload, discard safely
          }
        }
      }
    }

    // Process any remaining complete block in buffer
    if (buffer.trim()) {
      const lines = buffer.split("\n");
      let currentEvent = "";
      let currentData = "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("event:")) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith("data:")) {
          const dataSlice = trimmed.slice(5).trim();
          currentData = currentData ? currentData + "\n" + dataSlice : dataSlice;
        }
      }
      if (currentEvent && currentData) {
        try {
          const parsedData = JSON.parse(currentData);
          onEvent({
            event: currentEvent as any,
            data: parsedData,
          });
        } catch {
          // Discard malformed tail
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Non-streaming agent invocation.
 */
export async function sendAgentMessage(payload: AgentChatRequest): Promise<AgentChatResponse> {
  const token = apiClient.getToken();
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${baseUrl}/api/v1/agent/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...payload, stream: false }),
  });

  if (!response.ok) {
    let errorDetail = "";
    try {
      const errJson = await response.json();
      errorDetail = errJson.message || errJson.detail || "";
    } catch {
      // Body not JSON
    }
    throw new Error(formatAgentErrorMessage(response.status, errorDetail));
  }

  return (await response.json()) as AgentChatResponse;
}

/**
 * SSE streaming agent invocation with real-time event callbacks and cancellation support.
 */
export async function streamAgentMessage(
  payload: AgentChatRequest,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = apiClient.getToken();
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${baseUrl}/api/v1/agent/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  });

  if (!response.ok) {
    let errorDetail = "";
    try {
      const errJson = await response.json();
      errorDetail = errJson.message || errJson.detail || "";
    } catch {
      // Body not JSON
    }
    throw new Error(formatAgentErrorMessage(response.status, errorDetail));
  }

  if (!response.body) {
    throw new Error("Response body is not a readable stream.");
  }

  await parseSSEStream(response.body, onEvent);
}
