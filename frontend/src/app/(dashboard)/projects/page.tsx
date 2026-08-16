"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderGit2,
  Plus,
  GitBranch,
  Github,
  ExternalLink,
  ShieldCheck,
  Lock,
  Globe,
  Clock,
  Sparkles,
  Layers,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { GitHubImportWizard } from "@/components/projects/github-import-wizard";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showGitHubWizard, setShowGitHubWizard] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiClient.getProjects(),
    retry: 1,
  });

  const { data: orgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiClient.getOrganizations(),
    retry: 1,
  });

  const createProjectMutation = useMutation({
    mutationFn: async () => {
      let orgId = orgs && orgs.length > 0 ? orgs[0].id : null;
      if (!orgId) {
        const newOrg = await apiClient.createOrganization({ name: "Engineering Team" });
        orgId = newOrg.id;
      }
      return apiClient.createProject({
        name: projectName,
        description: projectDescription,
        organization_id: orgId,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowCreateModal(false);
      setProjectName("");
      setProjectDescription("");
    },
  });

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Projects & Workspaces
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Scoped tenant boundaries for linked GitHub repositories, branch indexing, and AI assistant sessions.
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <button
            onClick={() => setShowGitHubWizard(true)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg bg-primary text-primary-foreground shadow-md hover:opacity-90 transition-opacity"
          >
            <Github className="w-4 h-4" />
            <span>Import from GitHub</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg border bg-card hover:bg-muted text-foreground transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Blank Project</span>
          </button>
        </div>
      </div>

      {/* Projects Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-48 rounded-2xl border border-border/40 bg-card/40 animate-pulse p-6"
            />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => {
            const hasRepo = project.repositories && project.repositories.length > 0;
            const repo = hasRepo ? project.repositories![0] : null;

            return (
              <div
                key={project.id}
                className="p-6 rounded-2xl border border-border/50 bg-card/50 backdrop-blur-xl hover:border-primary/40 transition-all space-y-4 group flex flex-col justify-between"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary group-hover:scale-105 transition-transform">
                      <FolderGit2 className="w-5 h-5" />
                    </div>
                    {repo ? (
                      <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 flex items-center gap-1">
                        <Clock className="w-2.5 h-2.5" /> Ready to Index
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">
                        No Repo
                      </span>
                    )}
                  </div>

                  <div>
                    <h3 className="font-semibold text-base text-foreground group-hover:text-primary transition-colors">
                      {project.name}
                    </h3>
                    <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                      {project.description || "No description provided."}
                    </p>
                  </div>

                  {repo && (
                    <div className="p-3 rounded-xl bg-secondary/30 border border-border/40 space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 font-medium text-foreground">
                          <Github className="w-3.5 h-3.5 text-primary" />
                          <span className="truncate max-w-[180px]">{repo.full_name}</span>
                        </div>
                        {repo.html_url && (
                          <a
                            href={repo.html_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <GitBranch className="w-3 h-3 text-primary" /> {repo.default_branch}
                        </span>
                        {repo.is_private ? (
                          <span className="flex items-center gap-0.5 text-amber-500">
                            <Lock className="w-2.5 h-2.5" /> Private
                          </span>
                        ) : (
                          <span className="flex items-center gap-0.5 text-blue-500">
                            <Globe className="w-2.5 h-2.5" /> Public
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="text-[11px] font-mono">
                    ID: {project.id.slice(0, 8)}...
                  </span>
                  <span className="text-[10px] text-muted-foreground/60">
                    {new Date(project.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty State */
        <div className="p-12 text-center rounded-2xl border border-dashed border-border/60 bg-card/20 space-y-4 max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mx-auto">
            <FolderGit2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-base text-foreground">No Projects Created Yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
              Import a repository via GitHub App to set up a project ready for code indexing.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={() => setShowGitHubWizard(true)}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg bg-primary text-primary-foreground shadow-md hover:opacity-90 transition-opacity"
            >
              <Github className="w-4 h-4" />
              <span>Import GitHub Repository</span>
            </button>
          </div>
        </div>
      )}

      {/* GitHub Import Wizard Modal */}
      {showGitHubWizard && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <GitHubImportWizard
            organizations={orgs || []}
            onCancel={() => setShowGitHubWizard(false)}
            onSuccess={() => {
              setShowGitHubWizard(false);
              queryClient.invalidateQueries({ queryKey: ["projects"] });
            }}
          />
        </div>
      )}

      {/* Blank Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border/60 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-5">
            <div>
              <h3 className="text-base font-semibold text-foreground">Create Blank Project</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Set up a project container for repository indexing and assistant sessions.
              </p>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-muted-foreground font-medium mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Payments Microservice"
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>

              <div>
                <label className="block text-muted-foreground font-medium mb-1">
                  Description (Optional)
                </label>
                <textarea
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="e.g. Core transaction processing and ledger engine"
                  rows={3}
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => createProjectMutation.mutate()}
                disabled={!projectName.trim() || createProjectMutation.isPending}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {createProjectMutation.isPending ? "Creating..." : "Create Project"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
