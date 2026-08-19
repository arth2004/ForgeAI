"use client";

import React, { useState } from "react";
import { createPortal } from "react-dom";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowLeft,
  FolderGit2,
  GitBranch,
  Github,
  Search,
  FileCode,
  Layers,
  Settings,
  Sparkles,
  ExternalLink,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Project, Repository } from "@/types";
import { IndexStatusCard } from "@/components/indexing/IndexStatusCard";
import { FileExplorerTree } from "@/components/indexing/FileExplorerTree";
import { RetrievalSandbox } from "@/components/indexing/RetrievalSandbox";

export default function ProjectWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const projectId = params.id as string;

  const [activeTab, setActiveTab] = useState<"overview" | "retrieval" | "files">("overview");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: project, isLoading } = useQuery<Project>({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.getProject(projectId),
    enabled: !!projectId,
  });

  const repo: Repository | undefined =
    project?.repositories && project.repositories.length > 0
      ? project.repositories[0]
      : undefined;

  const handleDeleteProject = async () => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await apiClient.deleteProject(projectId);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.removeQueries({ queryKey: ["project", projectId] });
      setShowDeleteModal(false);
      router.push("/projects");
    } catch (err: any) {
      setDeleteError(err.message || "Failed to delete project. Please try again.");
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-slate-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
          <span>Loading project workspace...</span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-12 text-center">
        <h3 className="text-base font-semibold text-white">Project Not Found</h3>
        <p className="mt-1 text-xs text-slate-400">
          The requested project does not exist or you do not have permission to view it.
        </p>
        <Link
          href="/projects"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-xs font-semibold text-white"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Projects
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Navigation and Metadata */}
      <div className="flex flex-col gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Link href="/projects" className="hover:text-white transition-colors">
              Projects
            </Link>
            <span>/</span>
            <span className="text-slate-200">{project.name}</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white">{project.name}</h1>
            {repo && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-xs font-medium text-cyan-300">
                <Github className="h-3 w-3" />
                {repo.full_name}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400">
            {project.description || "Repository intelligence and code search workspace."}
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {repo?.html_url && (
            <a
              href={repo.html_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-slate-800/80 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700/80 hover:text-white transition-colors"
            >
              <Github className="h-4 w-4" />
              <span>GitHub Repository</span>
              <ExternalLink className="h-3 w-3 text-slate-400" />
            </a>
          )}

          <button
            type="button"
            onClick={() => setShowDeleteModal(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-300 hover:bg-rose-500/20 hover:border-rose-500/50 transition-colors"
            title="Delete project"
          >
            <Trash2 className="h-4 w-4 text-rose-400" />
            <span>Delete Project</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-white/10 gap-2">
        <button
          onClick={() => setActiveTab("overview")}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-medium transition-all ${
            activeTab === "overview"
              ? "border-cyan-500 text-cyan-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <Layers className="h-4 w-4" />
          <span>Overview & Index Status</span>
        </button>

        <button
          onClick={() => setActiveTab("retrieval")}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-medium transition-all ${
            activeTab === "retrieval"
              ? "border-cyan-500 text-cyan-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <Search className="h-4 w-4" />
          <span>Hybrid Retrieval Sandbox</span>
        </button>

        <button
          onClick={() => setActiveTab("files")}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-medium transition-all ${
            activeTab === "files"
              ? "border-cyan-500 text-cyan-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileCode className="h-4 w-4" />
          <span>Indexed Files & AST Chunks</span>
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === "overview" && repo && (
        <div className="space-y-6">
          <IndexStatusCard
            projectId={project.id}
            repository={repo}
          />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 backdrop-blur-md">
              <h3 className="text-sm font-semibold text-white">Code Intelligence Specs</h3>
              <dl className="mt-4 space-y-3 text-xs">
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <dt className="text-slate-400">Embedding Space</dt>
                  <dd className="font-mono text-cyan-300">gemini-embedding-2 (768d)</dd>
                </div>
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <dt className="text-slate-400">Vector Index Engine</dt>
                  <dd className="font-mono text-slate-200">pgvector HNSW (cosine, m=16, ef=64)</dd>
                </div>
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <dt className="text-slate-400">AST Parser Framework</dt>
                  <dd className="font-mono text-slate-200">Tree-sitter (TS, JS, Python, Markdown, JSON, YAML)</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Hybrid Fusion Algorithm</dt>
                  <dd className="font-mono text-slate-200">Reciprocal Rank Fusion (RRF, k=60)</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 backdrop-blur-md">
              <h3 className="text-sm font-semibold text-white">Explore Code Intelligence</h3>
              <p className="mt-1 text-xs text-slate-400">
                Inspect the searchable index or experiment with semantic queries and citation verification.
              </p>
              <div className="mt-4 space-y-2">
                <button
                  type="button"
                  onClick={() => setActiveTab("retrieval")}
                  className="w-full flex items-center justify-between rounded-lg border border-white/10 bg-slate-800/60 px-4 py-2.5 text-xs font-medium text-slate-200 hover:bg-slate-700/60 hover:text-white transition-colors"
                >
                  <span>Launch Hybrid Retrieval Sandbox</span>
                  <Search className="h-4 w-4 text-cyan-400" />
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("files")}
                  className="w-full flex items-center justify-between rounded-lg border border-white/10 bg-slate-800/60 px-4 py-2.5 text-xs font-medium text-slate-200 hover:bg-slate-700/60 hover:text-white transition-colors"
                >
                  <span>Browse Indexed Files & Semantic Chunks</span>
                  <FileCode className="h-4 w-4 text-indigo-400" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "retrieval" && <RetrievalSandbox projectId={project.id} />}

      {activeTab === "files" && <FileExplorerTree projectId={project.id} />}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 p-4 backdrop-blur-md animate-in fade-in-0">
            <div className="w-full max-w-md rounded-2xl border border-rose-500/30 bg-slate-900 p-6 shadow-2xl space-y-5">
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex-shrink-0">
                  <AlertTriangle className="h-6 w-6" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-base font-semibold text-white">Delete Project?</h3>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    This will permanently delete the Forge AI project <strong className="text-white font-medium">{project.name}</strong>, repository connection, indexed files, chunks, embeddings, and indexing metadata associated with this project.
                  </p>
                  <p className="text-xs text-rose-300/90 font-medium pt-1">
                    This does NOT delete the repository from GitHub.
                  </p>
                </div>
              </div>

              {deleteError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                  {deleteError}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/10">
                <button
                  type="button"
                  disabled={isDeleting}
                  onClick={() => setShowDeleteModal(false)}
                  className="rounded-lg border border-white/10 bg-slate-800/80 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700 hover:text-white transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isDeleting}
                  onClick={handleDeleteProject}
                  className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-rose-600/20 hover:bg-rose-500 transition-colors disabled:opacity-50"
                >
                  {isDeleting ? (
                    <>
                      <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Deleting Project...</span>
                    </>
                  ) : (
                    <>
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Delete Project</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
