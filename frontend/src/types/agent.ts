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
  branch_name?: string | null;
  current_commit_sha?: string | null;
  remote_branch_name?: string | null;
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

export interface PatchHunk {
  id: string;
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  old_content: string;
  new_content: string;
}

export interface PatchFile {
  file_path: string;
  operation: "CREATE" | "MODIFY" | "DELETE";
  old_content_hash?: string | null;
  new_content_hash?: string | null;
  hunks: PatchHunk[];
  reason?: string | null;
}

export interface AgentPatch {
  patch_id: string;
  workspace_id: string;
  session_id: string;
  status: "PROPOSED" | "VALIDATED" | "AWAITING_APPROVAL" | "APPROVED" | "APPLIED" | "REJECTED" | "CONFLICT" | "FAILED";
  summary: string;
  files: PatchFile[];
  diff_content?: string | null;
  approval_id?: string | null;
  created_at: string;
  applied_at?: string | null;
}

export interface PatchDiff {
  patch_id: string;
  workspace_id: string;
  unified_diff: string;
  files_changed: number;
  lines_added: number;
  lines_removed: number;
}

export interface TestCommand {
  runner: string;
  arguments: string[];
  working_directory?: string | null;
  timeout_seconds?: number;
}

export interface AgentTestExecution {
  test_id: string;
  workspace_id: string;
  session_id: string;
  patch_id?: string | null;
  test_command: TestCommand;
  status: "QUEUED" | "RUNNING" | "PASSED" | "FAILED" | "TIMEOUT" | "CANCELLED" | "SANDBOX_UNAVAILABLE";
  exit_code?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  duration_ms?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface AgentCommit {
  commit_id: string;
  workspace_id: string;
  session_id: string;
  branch_name: string;
  commit_sha: string;
  message: string;
  created_at: string;
}

export interface AgentPullRequest {
  pr_id: string;
  workspace_id: string;
  session_id: string;
  repository_id: string;
  branch_name: string;
  base_branch: string;
  commit_sha: string;
  github_pr_number?: number | null;
  github_pr_url?: string | null;
  title: string;
  body: string;
  status: "READY" | "CREATED" | "FAILED" | "CLOSED";
  created_at: string;
}

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
  patch?: AgentPatch | null;
  testExecution?: AgentTestExecution | null;
  commit?: AgentCommit | null;
  pullRequest?: AgentPullRequest | null;
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
  | "agent.workspace.failed"
  | "agent.patch.proposed"
  | "agent.patch.validated"
  | "agent.patch.applied"
  | "agent.patch.failed"
  | "agent.test.started"
  | "agent.test.completed"
  | "agent.test.failed"
  | "agent.branch.created"
  | "agent.commit.pending"
  | "agent.commit.created"
  | "agent.push.pending"
  | "agent.push.completed"
  | "agent.pr.pending"
  | "agent.pr.created"
  | "agent.git.error";

export interface AgentStreamEvent {
  event: AgentStreamEventType;
  data: Record<string, any>;
}



