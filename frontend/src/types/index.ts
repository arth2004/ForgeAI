export interface HealthStatus {
  status: "ok" | "degraded" | "down";
  version: string;
  services: {
    database: string;
    redis: string;
    worker_queue: string;
  };
  details?: Record<string, string>;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  github_user_id?: number | null;
  github_username?: string | null;
  github_installation_id?: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  settings?: Record<string, any>;
  repositories?: Repository[];
  created_at: string;
  updated_at: string;
}

export interface Repository {
  id: string;
  project_id: string;
  github_repo_id: number | null;
  owner?: string | null;
  full_name: string;
  default_branch: string;
  is_private: boolean;
  html_url?: string | null;
  description?: string | null;
  language?: string | null;
  indexing_status: "pending" | "indexing" | "ready" | "failed";
  created_at: string;
  updated_at: string;
}

export interface RepositoryBranch {
  id: string;
  repository_id: string;
  name: string;
  latest_commit_sha: string | null;
  is_protected: boolean;
  indexed_at: string | null;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface GitHubStatus {
  is_connected: boolean;
  github_user_id: number | null;
  github_username: string | null;
  github_installation_id: number | null;
  avatar_url: string | null;
}

export interface GitHubRepository {
  github_repo_id: number;
  name: string;
  full_name: string;
  owner: string | null;
  is_private: boolean;
  default_branch: string;
  html_url: string | null;
  description: string | null;
  language: string | null;
  updated_at: string | null;
}

export interface GitHubBranch {
  name: string;
  commit_sha: string | null;
  is_protected: boolean;
  is_default: boolean;
}

export interface CreateProjectFromGitHubPayload {
  organization_id: string;
  project_name: string;
  project_description?: string;
  github_repo_id: number;
  full_name: string;
  owner?: string;
  default_branch: string;
  selected_branch: string;
  latest_commit_sha?: string;
  is_private: boolean;
  html_url?: string;
  description?: string;
  language?: string;
}
