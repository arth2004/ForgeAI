export type ChangeType = "CREATE" | "MODIFY" | "DELETE" | "UNKNOWN";

export interface AffectedFile {
  file_path: string;
  change_type: ChangeType;
  reason: string;
  symbols: string[];
}

export interface ImplementationPlan {
  id: string;
  summary: string;
  problem_statement: string;
  approach: string;
  affected_files: AffectedFile[];
  new_files: string[];
  deleted_files: string[];
  symbols: string[];
  test_strategy: string;
  risks: string[];
  evidence?: AgentSource[];
  created_at: string;
}

export interface AgentApproval {
  approval_id: string;
  session_id: string;
  user_id: string;
  approval_type: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  workspace_id?: string | null;
  plan?: ImplementationPlan | null;
  created_at: string;
  resolved_at?: string | null;
}

export interface AgentWorkspace {
  workspace_id: string;
  session_id: string;
  organization_id: string;
  project_id: string;
  repository_id: string;
  branch_id?: string | null;
  user_id: string;
  status: string;
  path: string;
  base_commit_sha: string;
  created_at: string;
  expires_at: string;
  destroyed_at?: string | null;
}

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
  plan?: ImplementationPlan;
  approvalId?: string;
  approvalStatus?: string;
  workspace?: AgentWorkspace | null;
  error?: string | null;
  timestamp: string;
}

export type AgentStreamEventType =
  | "session.created"
  | "agent.started"
  | "agent.tool_call"
  | "agent.tool_result"
  | "agent.completed"
  | "agent.error"
  | "agent.plan.created"
  | "agent.approval.required"
  | "agent.approval.resolved"
  | "agent.workspace.created"
  | "agent.workspace.failed";

export interface AgentStreamEvent {
  event: AgentStreamEventType;
  data: Record<string, any>;
}

