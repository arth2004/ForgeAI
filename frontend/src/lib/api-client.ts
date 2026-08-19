import {
  AuthTokens,
  CreateProjectFromGitHubPayload,
  GitHubBranch,
  GitHubRepository,
  GitHubStatus,
  HealthStatus,
  Organization,
  Project,
  Repository,
  RepositoryBranch,
  User,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function extractToken(val: unknown): string | null {
  if (!val) return null;
  if (typeof val === "string") {
    const trimmed = val.trim();
    if (!trimmed) return null;
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("\"") && trimmed.endsWith("\""))
    ) {
      try {
        const parsed = JSON.parse(trimmed);
        return extractToken(parsed);
      } catch {
        // Not valid JSON, continue with raw string
      }
    }
    if (trimmed.startsWith("Bearer ")) {
      return trimmed.slice(7).trim();
    }
    return trimmed;
  }
  if (typeof val === "object" && val !== null) {
    const obj = val as Record<string, any>;
    if (obj.access_token && typeof obj.access_token === "string") {
      return extractToken(obj.access_token);
    }
    if (obj.token && typeof obj.token === "string") {
      return extractToken(obj.token);
    }
    if (obj.accessToken && typeof obj.accessToken === "string") {
      return extractToken(obj.accessToken);
    }
    if (obj.state && typeof obj.state === "object") {
      return extractToken(obj.state);
    }
  }
  return null;
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      this.token = this.getToken();
    }
  }

  public setToken(token: string | null) {
    this.token = token;
    if (typeof window !== "undefined") {
      if (token) {
        localStorage.setItem("forgeai_token", token);
      } else {
        localStorage.removeItem("forgeai_token");
        localStorage.removeItem("forgeai_auth");
        localStorage.removeItem("auth_token");
        localStorage.removeItem("access_token");
      }
    }
  }

  public getToken(): string | null {
    if (typeof window === "undefined") {
      return this.token;
    }

    const candidateKeys = [
      "forgeai_token",
      "forgeai_auth",
      "auth_token",
    ];

    // 1. Check candidate keys in localStorage
    for (const key of candidateKeys) {
      try {
        const item = localStorage.getItem(key);
        const tok = extractToken(item);
        if (tok) {
          this.token = tok;
          return tok;
        }
      } catch {}
    }

    // 2. Fallback: check candidate keys in sessionStorage
    for (const key of candidateKeys) {
      try {
        const item = sessionStorage.getItem(key);
        const tok = extractToken(item);
        if (tok) {
          this.token = tok;
          return tok;
        }
      } catch {}
    }

    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}/api/v1${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          if (typeof errorJson.detail === "string") {
            errorMessage = errorJson.detail;
          } else if (Array.isArray(errorJson.detail)) {
            errorMessage = errorJson.detail
              .map((e: any) => {
                const loc = Array.isArray(e.loc) ? e.loc.join(" → ") : "";
                return loc ? `${loc}: ${e.msg}` : e.msg;
              })
              .join("; ");
          } else {
            errorMessage = String(errorJson.detail);
          }
        } else if (errorJson.message) {
          errorMessage = errorJson.message;
        }
      } catch {
        // Fall back to status text
      }
      throw new Error(errorMessage);
    }

    return response.json() as Promise<T>;
  }

  // Health
  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>("/health");
  }

  // Auth
  async register(data: {
    email: string;
    password: string;
    full_name?: string;
    organization_name?: string;
  }): Promise<AuthTokens> {
    const res = await this.request<AuthTokens>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
    this.setToken(res.access_token);
    return res;
  }

  async login(data: { email: string; password: string }): Promise<AuthTokens> {
    const res = await this.request<AuthTokens>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    });
    this.setToken(res.access_token);
    return res;
  }

  async getMe(): Promise<User> {
    return this.request<User>("/auth/me");
  }

  logout() {
    this.setToken(null);
  }

  // Organizations
  async getOrganizations(): Promise<Organization[]> {
    return this.request<Organization[]>("/organizations");
  }

  async createOrganization(data: { name: string; slug?: string }): Promise<Organization> {
    return this.request<Organization>("/organizations", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Projects
  async getProjects(organizationId?: string): Promise<Project[]> {
    const query = organizationId ? `?organization_id=${organizationId}` : "";
    return this.request<Project[]>(`/projects${query}`);
  }

  async getProject(id: string): Promise<Project> {
    return this.request<Project>(`/projects/${id}`);
  }

  async createProject(data: {
    name: string;
    organization_id: string;
    description?: string;
  }): Promise<Project> {
    return this.request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteProject(id: string): Promise<{ message: string; id: string }> {
    return this.request<{ message: string; id: string }>(`/projects/${id}`, {
      method: "DELETE",
    });
  }

  // Repositories
  async getRepositories(projectId: string): Promise<Repository[]> {
    return this.request<Repository[]>(`/projects/${projectId}/repositories`);
  }

  async connectRepository(
    projectId: string,
    data: {
      full_name: string;
      default_branch?: string;
      is_private?: boolean;
    }
  ): Promise<Repository> {
    return this.request<Repository>(`/projects/${projectId}/repositories`, {
      method: "POST",
      body: JSON.stringify({ ...data, project_id: projectId }),
    });
  }

  // GitHub Integration
  async getGitHubStatus(): Promise<GitHubStatus> {
    return this.request<GitHubStatus>("/github/status");
  }

  async getGitHubAuthorizeUrl(): Promise<{ authorization_url: string }> {
    return this.request<{ authorization_url: string }>("/github/authorize");
  }

  async disconnectGitHub(): Promise<GitHubStatus> {
    return this.request<GitHubStatus>("/github/disconnect", {
      method: "DELETE",
    });
  }

  async getGitHubRepositories(
    page: number = 1,
    perPage: number = 30
  ): Promise<{ repositories: GitHubRepository[]; total_count: number; page: number; per_page: number }> {
    return this.request(`/github/repositories?page=${page}&per_page=${perPage}`);
  }

  async getGitHubBranches(
    owner: string,
    repo: string,
    defaultBranch: string = "main"
  ): Promise<GitHubBranch[]> {
    return this.request<GitHubBranch[]>(
      `/github/repositories/${owner}/${repo}/branches?default_branch=${encodeURIComponent(defaultBranch)}`
    );
  }

  async createProjectFromGitHub(
    payload: CreateProjectFromGitHubPayload
  ): Promise<{
    project: Project;
    repository: Repository;
    selected_branch: RepositoryBranch;
    status: string;
    message: string;
  }> {
    return this.request("/github/projects/create-from-repo", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // Worker
  async triggerWorkerTest(message: string = "ping"): Promise<{ job_id: string; status: string }> {
    return this.request<{ job_id: string; status: string }>("/worker/test-job", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  }

  async getWorkerJobStatus(jobId: string): Promise<{ job_id: string; status: string; result?: any }> {
    return this.request<{ job_id: string; status: string; result?: any }>(`/worker/test-job/${jobId}`);
  }

  // Repository Intelligence & Search
  async triggerIndexing(
    projectId: string,
    repoId: string,
    isFullReindex: boolean = false,
    branchId?: string
  ): Promise<any> {
    return this.request(`/projects/${projectId}/repositories/${repoId}/index`, {
      method: "POST",
      body: JSON.stringify({ is_full_reindex: isFullReindex, branch_id: branchId }),
    });
  }

  async getIndexingStatus(projectId: string, repoId: string): Promise<any> {
    return this.request(`/projects/${projectId}/repositories/${repoId}/index/status`);
  }

  async searchHybrid(
    projectId: string,
    query: string,
    branchId?: string,
    topK: number = 15
  ): Promise<any> {
    return this.request(`/projects/${projectId}/search/hybrid`, {
      method: "POST",
      body: JSON.stringify({ query, branch_id: branchId, top_k: topK }),
    });
  }

  async listIndexedFiles(projectId: string, branchId?: string): Promise<any[]> {
    const q = branchId ? `?branch_id=${branchId}` : "";
    return this.request(`/projects/${projectId}/files${q}`);
  }

  async getFileDetail(projectId: string, fileId: string): Promise<any> {
    return this.request(`/projects/${projectId}/files/${fileId}`);
  }
}

export const apiClient = new ApiClient();
