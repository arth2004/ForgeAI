"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { GitHubBranch, GitHubRepository, Organization } from "@/types";
import {
  Github,
  Search,
  Lock,
  Globe,
  GitBranch,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FolderGit2,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
} from "lucide-react";

interface GitHubImportWizardProps {
  organizations: Organization[];
  onSuccess: (projectId: string) => void;
  onCancel: () => void;
}

export function GitHubImportWizard({
  organizations,
  onSuccess,
  onCancel,
}: GitHubImportWizardProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState(
    organizations[0]?.id || ""
  );
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepository | null>(
    null
  );
  const [selectedBranch, setSelectedBranch] = useState<string>("main");
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  // 1. GitHub Status Query
  const { data: githubStatus, isLoading: statusLoading } = useQuery({
    queryKey: ["github-status"],
    queryFn: () => apiClient.getGitHubStatus(),
  });

  // 2. Repositories Query (when connected)
  const { data: repoData, isLoading: reposLoading } = useQuery({
    queryKey: ["github-repositories"],
    queryFn: () => apiClient.getGitHubRepositories(1, 100),
    enabled: !!githubStatus?.is_connected,
  });

  // 3. Branches Query (when repo selected)
  const { data: branches, isLoading: branchesLoading } = useQuery({
    queryKey: ["github-branches", selectedRepo?.owner, selectedRepo?.name],
    queryFn: () =>
      apiClient.getGitHubBranches(
        selectedRepo!.owner || "",
        selectedRepo!.name,
        selectedRepo!.default_branch
      ),
    enabled: !!selectedRepo && !!selectedRepo.owner,
  });

  // 4. Connect GitHub Handler
  const connectGitHubMutation = useMutation({
    mutationFn: () => apiClient.getGitHubAuthorizeUrl(),
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (err: any) => {
      setError(err.message || "Failed to initialize GitHub authorization.");
    },
  });

  // 5. Create Project Mutation
  const createProjectMutation = useMutation({
    mutationFn: () => {
      if (!selectedRepo) throw new Error("No repository selected.");
      return apiClient.createProjectFromGitHub({
        organization_id: selectedOrgId,
        project_name: projectName || selectedRepo.name,
        project_description: projectDescription || selectedRepo.description || undefined,
        github_repo_id: selectedRepo.github_repo_id,
        full_name: selectedRepo.full_name,
        owner: selectedRepo.owner || undefined,
        default_branch: selectedRepo.default_branch,
        selected_branch: selectedBranch,
        is_private: selectedRepo.is_private,
        html_url: selectedRepo.html_url || undefined,
        description: selectedRepo.description || undefined,
        language: selectedRepo.language || undefined,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      onSuccess(data.project.id);
    },
    onError: (err: any) => {
      setError(err.message || "Failed to create project from GitHub repository.");
    },
  });

  // Filter repos by search
  const filteredRepos = (repoData?.repositories || []).filter((r) =>
    r.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="bg-card text-card-foreground border rounded-xl shadow-xl max-w-2xl w-full p-6 space-y-6">
      {/* Wizard Header & Progress */}
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Github className="w-5 h-5 text-primary" />
            Import GitHub Repository
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Phase 2: Authorize, discover, and link your repository
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-medium">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${
                step === i
                  ? "bg-primary text-primary-foreground font-bold ring-2 ring-primary/30"
                  : step > i
                  ? "bg-primary/20 text-primary"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {step > i ? <CheckCircle2 className="w-3.5 h-3.5" /> : i}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* STEP 1: GitHub Connection Check */}
      {step === 1 && (
        <div className="space-y-4 py-2">
          {statusLoading ? (
            <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Checking GitHub connection...</span>
            </div>
          ) : githubStatus?.is_connected ? (
            <div className="p-4 rounded-lg border bg-accent/40 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center font-bold text-primary">
                    {githubStatus.github_username?.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">
                      @{githubStatus.github_username}
                    </p>
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                      GitHub App Connected (Read-Only: Contents & Metadata)
                    </p>
                  </div>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 font-medium border border-emerald-500/20">
                  Ready
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Your account is authorized to discover and import repositories configured in your GitHub App installation.
              </p>
            </div>
          ) : (
            <div className="text-center py-8 space-y-4">
              <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                <Github className="w-8 h-8" />
              </div>
              <div className="space-y-1">
                <h3 className="font-semibold text-base">Connect Your GitHub Account</h3>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Authorize Forge AI to read repository metadata and code structures with fine-grained, read-only permissions.
                </p>
              </div>
              <button
                onClick={() => connectGitHubMutation.mutate()}
                disabled={connectGitHubMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground font-medium rounded-lg hover:opacity-90 transition-opacity text-sm shadow-sm"
              >
                {connectGitHubMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Github className="w-4 h-4" />
                )}
                Connect GitHub
              </button>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4 border-t">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm rounded-lg border hover:bg-muted font-medium transition-colors"
            >
              Cancel
            </button>
            {githubStatus?.is_connected && (
              <button
                onClick={() => setStep(2)}
                className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium flex items-center gap-1.5 hover:opacity-90 transition-opacity"
              >
                Select Repository
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* STEP 2: Repository Selection */}
      {step === 2 && (
        <div className="space-y-4 py-2">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search repositories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>

          <div className="border rounded-lg max-h-64 overflow-y-auto divide-y">
            {reposLoading ? (
              <div className="p-8 text-center text-muted-foreground flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Loading repositories from GitHub...</span>
              </div>
            ) : filteredRepos.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm">
                No repositories found matching "{searchQuery}". Make sure the repository is added to your GitHub App installation.
              </div>
            ) : (
              filteredRepos.map((repo) => (
                <div
                  key={repo.github_repo_id}
                  onClick={() => {
                    setSelectedRepo(repo);
                    setSelectedBranch(repo.default_branch);
                    setProjectName(repo.name);
                    setProjectDescription(repo.description || "");
                  }}
                  className={`p-3.5 flex items-center justify-between cursor-pointer hover:bg-muted/50 transition-colors ${
                    selectedRepo?.github_repo_id === repo.github_repo_id
                      ? "bg-primary/10 border-l-4 border-l-primary"
                      : ""
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <FolderGit2 className="w-4 h-4 text-primary" />
                      <span className="font-medium text-sm">{repo.full_name}</span>
                      {repo.is_private ? (
                        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 font-medium border border-amber-500/20">
                          <Lock className="w-2.5 h-2.5" /> Private
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 font-medium border border-blue-500/20">
                          <Globe className="w-2.5 h-2.5" /> Public
                        </span>
                      )}
                    </div>
                    {repo.description && (
                      <p className="text-xs text-muted-foreground line-clamp-1">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <div className="text-right text-xs text-muted-foreground flex items-center gap-3">
                    {repo.language && (
                      <span className="px-2 py-0.5 rounded bg-muted font-medium">
                        {repo.language}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <GitBranch className="w-3 h-3" /> {repo.default_branch}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="flex justify-between items-center pt-4 border-t">
            <button
              onClick={() => setStep(1)}
              className="px-4 py-2 text-sm rounded-lg border hover:bg-muted font-medium flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={!selectedRepo}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium flex items-center gap-1.5 hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              Select Branch
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Branch Selection */}
      {step === 3 && (
        <div className="space-y-4 py-2">
          <div className="p-3 rounded-lg border bg-muted/40 space-y-1">
            <p className="text-xs text-muted-foreground">Selected Repository</p>
            <p className="font-semibold text-sm flex items-center gap-2">
              <FolderGit2 className="w-4 h-4 text-primary" />
              {selectedRepo?.full_name}
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Target Branch for Ingestion</label>
            {branchesLoading ? (
              <div className="p-6 text-center text-muted-foreground flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Loading repository branches...</span>
              </div>
            ) : (
              <div className="border rounded-lg divide-y max-h-56 overflow-y-auto">
                {(branches || []).map((b) => (
                  <div
                    key={b.name}
                    onClick={() => setSelectedBranch(b.name)}
                    className={`p-3 flex items-center justify-between cursor-pointer hover:bg-muted/50 transition-colors ${
                      selectedBranch === b.name
                        ? "bg-primary/10 border-l-4 border-l-primary"
                        : ""
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <GitBranch className="w-4 h-4 text-primary" />
                      <span className="font-medium text-sm">{b.name}</span>
                      {b.is_default && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary font-bold">
                          default
                        </span>
                      )}
                      {b.is_protected && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 font-medium">
                          protected
                        </span>
                      )}
                    </div>
                    {b.commit_sha && (
                      <span className="text-xs font-mono text-muted-foreground">
                        {b.commit_sha.substring(0, 7)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-between items-center pt-4 border-t">
            <button
              onClick={() => setStep(2)}
              className="px-4 py-2 text-sm rounded-lg border hover:bg-muted font-medium flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={() => setStep(4)}
              disabled={!selectedBranch}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium flex items-center gap-1.5 hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              Project Details
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: Project Details & Create */}
      {step === 4 && (
        <div className="space-y-4 py-2">
          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                Organization
              </label>
              <select
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                Project Name
              </label>
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="e.g. Core Engine"
                className="w-full px-3 py-2 text-sm rounded-lg border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 font-medium"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                Description (Optional)
              </label>
              <textarea
                value={projectDescription}
                onChange={(e) => setProjectDescription(e.target.value)}
                rows={2}
                placeholder="Brief summary of the project codebase..."
                className="w-full px-3 py-2 text-sm rounded-lg border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            <div className="p-3 rounded-lg border bg-accent/40 space-y-1.5 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Repository:</span>
                <span className="font-semibold text-foreground">{selectedRepo?.full_name}</span>
              </div>
              <div className="flex justify-between">
                <span>Branch:</span>
                <span className="font-semibold text-foreground">{selectedBranch}</span>
              </div>
              <div className="flex justify-between">
                <span>Initial Status:</span>
                <span className="font-semibold text-amber-500">Ready to Index (Pending)</span>
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center pt-4 border-t">
            <button
              onClick={() => setStep(3)}
              className="px-4 py-2 text-sm rounded-lg border hover:bg-muted font-medium flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={() => createProjectMutation.mutate()}
              disabled={createProjectMutation.isPending || !projectName}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-bold flex items-center gap-2 hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {createProjectMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Creating Project...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  Create Project & Link Repo
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
