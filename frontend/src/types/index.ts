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
  created_at: string;
  updated_at: string;
}

export interface Repository {
  id: string;
  project_id: string;
  github_repo_id: number | null;
  full_name: string;
  default_branch: string;
  is_private: boolean;
  indexing_status: "pending" | "indexing" | "ready" | "failed";
  created_at: string;
  updated_at: string;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  expires_in: number;
}
