"use client";

import React from "react";
import {
  GitPullRequest,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  Clock,
  ShieldAlert,
  GitBranch,
  ArrowRight,
  User,
} from "lucide-react";
import { PRReviewTask } from "@/types/agent";
import { AgentReviewFindings } from "./AgentReviewFindings";

interface PullRequestReviewCardProps {
  reviewTask: PRReviewTask;
}

export const PullRequestReviewCard: React.FC<PullRequestReviewCardProps> = ({ reviewTask }) => {
  const snapshot = reviewTask.snapshot;
  const isFailed = reviewTask.lifecycle_state === "FAILED";
  const isStale = reviewTask.lifecycle_state === "STALE";
  const isReady = reviewTask.lifecycle_state === "REVIEW_READY";
  const isAnalyzing = reviewTask.lifecycle_state === "ANALYZING" || reviewTask.lifecycle_state === "QUEUED";

  return (
    <div
      data-testid="pr-review-card"
      className={`rounded-xl border transition-all duration-200 overflow-hidden ${
        isFailed
          ? "bg-rose-950/20 border-rose-800/60"
          : isStale
          ? "bg-amber-950/20 border-amber-800/60"
          : isReady
          ? "bg-zinc-900/90 border-zinc-800"
          : "bg-zinc-900/60 border-zinc-800/80"
      }`}
    >
      {/* Top Banner & Metadata */}
      <div className="p-4 border-b border-zinc-800/80 bg-zinc-900/40">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <GitPullRequest className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-mono text-xs font-semibold text-indigo-400">
                  PR #{snapshot?.pr_number || "?"}
                </span>
                <h3 className="text-sm font-semibold text-zinc-100">
                  {snapshot?.title || "Pull Request Review"}
                </h3>
              </div>
              <div className="flex items-center space-x-3 text-xs text-zinc-400 mt-1">
                {snapshot?.author_username && (
                  <span className="flex items-center space-x-1">
                    <User className="w-3.5 h-3.5" />
                    <span>{snapshot.author_username}</span>
                  </span>
                )}
                <span className="flex items-center space-x-1 font-mono text-[11px] text-zinc-400">
                  <GitBranch className="w-3 h-3 text-zinc-400" />
                  <span>{snapshot?.base_branch || "main"}</span>
                  <ArrowRight className="w-3 h-3 text-zinc-400" />
                  <span className="text-zinc-200">{snapshot?.head_branch || "branch"}</span>
                  <span className="text-zinc-400">({snapshot?.head_sha ? snapshot.head_sha.slice(0, 7) : ""})</span>
                </span>
              </div>
            </div>
          </div>

          {/* Status Badge */}
          <div className="flex items-center space-x-2">
            {isFailed && (
              <span
                data-testid="pr-review-failed-badge"
                className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40"
              >
                <AlertCircle className="w-3.5 h-3.5" />
                <span>FAILED</span>
              </span>
            )}
            {isStale && (
              <span
                data-testid="pr-review-stale-badge"
                className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>STALE</span>
              </span>
            )}
            {isReady && (
              <span
                data-testid="pr-review-ready-badge"
                className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
              >
                <CheckCircle className="w-3.5 h-3.5" />
                <span>REVIEW READY</span>
              </span>
            )}
            {isAnalyzing && (
              <span
                data-testid="pr-review-analyzing-badge"
                className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 animate-pulse"
              >
                <Clock className="w-3.5 h-3.5" />
                <span>ANALYZING</span>
              </span>
            )}
          </div>
        </div>

        {/* Stale Review Warning Banner */}
        {isStale && (
          <div
            data-testid="pr-review-stale-warning"
            className="mt-3 p-2.5 rounded-lg bg-amber-950/40 border border-amber-800/80 text-xs text-amber-200 flex items-center space-x-2"
          >
            <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Outdated Review:</strong> A newer commit was pushed to this pull request on GitHub. This review snapshot ({snapshot?.head_sha.slice(0, 7)}) is superseded.
            </span>
          </div>
        )}
      </div>

      {/* Review Findings Section (Read-Only) */}
      <div className="p-4">
        {isFailed ? (
          <div
            data-testid="pr-review-failed-banner"
            className="p-4 rounded-lg bg-rose-950/30 border border-rose-900/50 text-xs text-rose-200"
          >
            <div className="flex items-center space-x-2 font-semibold text-rose-300 mb-1">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>Reviewer unavailable</span>
            </div>
            <p className="text-zinc-300">
              The AI model could not complete this review.
            </p>
            {reviewTask.failure_reason && (
              <div className="mt-2 p-2 rounded bg-black/40 border border-rose-900/30 font-mono text-[11px] text-rose-300/90 break-words">
                <strong>Reason:</strong> {reviewTask.failure_reason}
              </div>
            )}
          </div>
        ) : reviewTask.findings && reviewTask.findings.length > 0 ? (
          <AgentReviewFindings findings={reviewTask.findings} />
        ) : isReady ? (
          <div className="p-4 text-center rounded-lg bg-emerald-950/20 border border-emerald-900/40 text-xs text-emerald-300">
            <CheckCircle className="w-5 h-5 mx-auto mb-1.5 text-emerald-400" />
            <span>No security or regression findings detected on this Pull Request snapshot.</span>
          </div>
        ) : (
          <div className="p-4 text-center rounded-lg bg-zinc-950/40 border border-zinc-800/50 text-xs text-zinc-400">
            <span>Review analysis in progress...</span>
          </div>
        )}
      </div>
    </div>
  );
};
