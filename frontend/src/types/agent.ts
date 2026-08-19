export interface AgentSource {
  file_path: string;
  symbol_name?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  commit_sha?: string | null;
}

export interface AgentChatMetadata {
  iterations: number;
  tool_calls: number;
  duration_ms: number;
  retrieved_sources_count: number;
}

export interface AgentChatRequest {
  message: string;
  project_id: string;
  repository_id?: string | null;
  branch_id?: string | null;
  session_id?: string | null;
  stream?: boolean;
}

export interface AgentChatResponse {
  session_id: string;
  project_id: string;
  repository_id?: string | null;
  branch_id?: string | null;
  answer: string;
  sources: AgentSource[];
  metadata: AgentChatMetadata;
}

export interface AgentToolActivity {
  id: string;
  tool: string;
  status: "running" | "success" | "failed";
  iteration?: number;
  duration_ms?: number;
  error?: string | null;
}

export type MessageRole = "user" | "assistant";
export type MessageStatus = "idle" | "sending" | "streaming" | "completed" | "error";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  sources?: AgentSource[];
  toolActivities?: AgentToolActivity[];
  error?: string | null;
  timestamp: string;
}

export type AgentStreamEventType =
  | "session.created"
  | "agent.started"
  | "agent.tool_call"
  | "agent.tool_result"
  | "agent.completed"
  | "agent.error";

export interface AgentStreamEvent {
  event: AgentStreamEventType;
  data: Record<string, any>;
}
