"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderGit2,
  Plus,
  GitBranch,
  Layers,
  Sparkles,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
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
        // Create a default org if none exist
        const newOrg = await apiClient.createOrganization({ name: "Default Team" });
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
            Scoped tenant boundaries for linked repositories, indexes, and AI assistant sessions.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-sky-500 hover:bg-sky-400 text-white shadow-md shadow-sky-500/20 transition-colors self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* Projects Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-44 rounded-2xl border border-border/40 bg-card/40 animate-pulse p-6"
            />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <div
              key={project.id}
              className="p-6 rounded-2xl border border-border/50 bg-card/50 backdrop-blur-xl hover:border-sky-500/30 transition-all space-y-4 group"
            >
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 group-hover:scale-105 transition-transform">
                  <FolderGit2 className="w-5 h-5" />
                </div>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-secondary/80 text-muted-foreground">
                  Active
                </span>
              </div>

              <div>
                <h3 className="font-semibold text-base text-foreground group-hover:text-sky-400 transition-colors">
                  {project.name}
                </h3>
                <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                  {project.description || "No description provided."}
                </p>
              </div>

              <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  <GitBranch className="w-3.5 h-3.5 text-sky-400" />
                  <span>Phase 2: Connect Repo</span>
                </div>
                <span className="text-[10px] text-muted-foreground/60">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Empty State */
        <div className="p-12 text-center rounded-2xl border border-dashed border-border/60 bg-card/20 space-y-4 max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 mx-auto">
            <FolderGit2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-base text-foreground">No Projects Created Yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
              Create a project to initialize multi-tenant ownership boundaries for repositories.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-sky-500 hover:bg-sky-400 text-white shadow-md shadow-sky-500/20 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Create First Project</span>
          </button>
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border/60 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-5">
            <div>
              <h3 className="text-base font-semibold text-foreground">Create New Project</h3>
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
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
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
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
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
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-sky-500 hover:bg-sky-400 text-white disabled:opacity-50 transition-colors"
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
