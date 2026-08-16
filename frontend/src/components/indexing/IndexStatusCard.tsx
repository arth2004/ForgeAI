"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { apiClient } from "@/lib/api-client";
import { IndexingJob, Repository } from "@/types";

interface IndexStatusCardProps {
  projectId: string;
  repository: Repository;
  onIndexUpdated?: () => void;
}

export function IndexStatusCard({
  projectId,
  repository,
  onIndexUpdated,
}: IndexStatusCardProps) {
  const [job, setJob] = useState<IndexingJob | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [isFullReindex, setIsFullReindex] = useState<boolean>(false);
  const [showOptionsModal, setShowOptionsModal] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchStatus = async () => {
    try {
      const data = await apiClient.getIndexingStatus(projectId, repository.id);
      setJob(data);
      if (data.status === "completed" || data.status === "ready") {
        if (onIndexUpdated) onIndexUpdated();
      }
    } catch {
      // No active job yet
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(() => {
      if (
        repository.indexing_status === "indexing" ||
        job?.status === "acquiring" ||
        job?.status === "parsing" ||
        job?.status === "embedding" ||
        job?.status === "pending"
      ) {
        fetchStatus();
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [projectId, repository.id, repository.indexing_status, job?.status]);

  const handleTriggerIndex = async (full: boolean) => {
    setTriggering(true);
    setShowOptionsModal(false);
    try {
      const data = await apiClient.triggerIndexing(projectId, repository.id, full);
      setJob(data);
      if (onIndexUpdated) onIndexUpdated();
    } catch (err: any) {
      alert(`Failed to trigger indexing: ${err.message}`);
    } finally {
      setTriggering(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "ready":
      case "completed":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "indexing":
      case "acquiring":
      case "parsing":
      case "embedding":
        return "bg-cyan-500/10 text-cyan-400 border-cyan-500/20 animate-pulse";
      case "failed":
        return "bg-rose-500/10 text-rose-400 border-rose-500/20";
      default:
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    }
  };

  const currentStatus = job?.status || repository.indexing_status;
  const isCurrentlyIndexing =
    currentStatus === "indexing" ||
    currentStatus === "acquiring" ||
    currentStatus === "parsing" ||
    currentStatus === "embedding";

  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 backdrop-blur-md">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-white">Repository Intelligence Index</h3>
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider ${getStatusColor(
                currentStatus
              )}`}
            >
              {currentStatus}
            </span>
          </div>
          <p className="text-sm text-slate-400">
            Semantic AST parsing, gemini-embedding-2 (768d), and pgvector HNSW indexing
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowOptionsModal(true)}
            disabled={isCurrentlyIndexing || triggering}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-500/20 transition-all hover:bg-cyan-500 disabled:opacity-50"
          >
            {isCurrentlyIndexing ? (
              <>
                <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <span>Indexing in Progress...</span>
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                <span>Sync / Re-index</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Progress & Metrics */}
      <div className="mt-6 grid grid-cols-2 gap-4 border-t border-white/5 pt-4 sm:grid-cols-4">
        <div className="rounded-lg bg-slate-800/40 p-3">
          <div className="text-xs text-slate-400">Indexed Files</div>
          <div className="mt-1 text-xl font-bold text-white">
            {job ? `${job.processed_files} / ${job.total_files || "-"}` : "-"}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/40 p-3">
          <div className="text-xs text-slate-400">Semantic Chunks</div>
          <div className="mt-1 text-xl font-bold text-white">
            {job?.total_chunks ?? "-"}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/40 p-3">
          <div className="text-xs text-slate-400">Embedded Vectors</div>
          <div className="mt-1 text-xl font-bold text-cyan-400">
            {job?.embedded_chunks ?? "-"}
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/40 p-3">
          <div className="text-xs text-slate-400">Target Commit</div>
          <div className="mt-1 font-mono text-xs text-slate-300">
            {job?.commit_sha ? job.commit_sha.slice(0, 10) : repository.default_branch}
          </div>
        </div>
      </div>

      {/* Live Error Notification if Failed */}
      {job?.error_message && (
        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
          <span className="font-semibold">Indexing Alert:</span> {job.error_message}
        </div>
      )}

      {/* Re-indexing Confirmation Modal rendered at document.body via Portal */}
      {showOptionsModal &&
        mounted &&
        createPortal(
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
            <div
              className="relative w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900/95 p-6 shadow-2xl backdrop-blur-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <h4 className="text-lg font-semibold text-white">Index Repository Codebase</h4>
              <p className="mt-2 text-sm text-slate-300">
                Select your indexing mode for repository{" "}
                <code className="rounded bg-cyan-500/10 px-1.5 py-0.5 font-mono text-xs text-cyan-300">
                  {repository.full_name}
                </code>
                :
              </p>

              <div className="mt-5 space-y-3">
                <label
                  onClick={() => setIsFullReindex(false)}
                  className={`flex cursor-pointer items-start gap-3.5 rounded-xl border p-4 transition-all ${
                    !isFullReindex
                      ? "border-cyan-500/60 bg-cyan-500/10 shadow-sm shadow-cyan-500/10"
                      : "border-white/10 bg-slate-800/40 hover:border-white/20 hover:bg-slate-800/60"
                  }`}
                >
                  <input
                    type="radio"
                    name="index_mode"
                    checked={!isFullReindex}
                    onChange={() => setIsFullReindex(false)}
                    className="mt-1 h-4 w-4 border-white/20 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  <div>
                    <div className="text-sm font-semibold text-white">Incremental Delta Indexing (Fast)</div>
                    <div className="mt-0.5 text-xs leading-relaxed text-slate-400">
                      Compares SHA-256 hashes. Only parses and embeds modified/new files. Re-uses existing vectors.
                    </div>
                  </div>
                </label>

                <label
                  onClick={() => setIsFullReindex(true)}
                  className={`flex cursor-pointer items-start gap-3.5 rounded-xl border p-4 transition-all ${
                    isFullReindex
                      ? "border-cyan-500/60 bg-cyan-500/10 shadow-sm shadow-cyan-500/10"
                      : "border-white/10 bg-slate-800/40 hover:border-white/20 hover:bg-slate-800/60"
                  }`}
                >
                  <input
                    type="radio"
                    name="index_mode"
                    checked={isFullReindex}
                    onChange={() => setIsFullReindex(true)}
                    className="mt-1 h-4 w-4 border-white/20 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  <div>
                    <div className="text-sm font-semibold text-white">Full Clean Re-index</div>
                    <div className="mt-0.5 text-xs leading-relaxed text-slate-400">
                      Re-extracts AST, re-chunks all files, and regenerates all embeddings from scratch into a fresh version.
                    </div>
                  </div>
                </label>
              </div>

              <div className="mt-6 flex items-center justify-end gap-3 border-t border-white/10 pt-4">
                <button
                  type="button"
                  onClick={() => setShowOptionsModal(false)}
                  className="rounded-lg border border-white/10 px-4 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerIndex(isFullReindex)}
                  className="rounded-lg bg-cyan-600 px-5 py-2 text-xs font-semibold text-white shadow-md shadow-cyan-600/20 transition-colors hover:bg-cyan-500"
                >
                  Start Indexing
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
