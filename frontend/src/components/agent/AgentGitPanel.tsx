"use client";

import React, { useState } from "react";
import { AgentCommit, AgentPullRequest, AgentWorkspace } from "@/types/agent";

interface AgentGitPanelProps {
  workspace: AgentWorkspace;
  commit?: AgentCommit | null;
  pullRequest?: AgentPullRequest | null;
  onCommit?: (workspaceId: string, message?: string) => Promise<void>;
  onPush?: (workspaceId: string) => Promise<void>;
  onCreatePR?: (workspaceId: string, title?: string, body?: string) => Promise<void>;
}

export const AgentGitPanel: React.FC<AgentGitPanelProps> = ({
  workspace,
  commit,
  pullRequest,
  onCommit,
  onPush,
  onCreatePR,
}) => {
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [commitStatus, setCommitStatus] = useState<"IDLE" | "APPROVED" | "COMMITTED">(
    commit ? "COMMITTED" : "IDLE"
  );
  const [pushStatus, setPushStatus] = useState<"IDLE" | "APPROVED" | "PUSHED">(
    workspace.remote_branch_name ? "PUSHED" : "IDLE"
  );
  const [prStatus, setPrStatus] = useState<"IDLE" | "APPROVED" | "CREATED">(
    pullRequest ? "CREATED" : "IDLE"
  );

  const handleApproveCommit = () => {
    setCommitStatus("APPROVED");
  };

  const handleCommit = async () => {
    if (!onCommit) return;
    setIsActionLoading(true);
    setActionError(null);
    try {
      await onCommit(workspace.workspace_id);
      setCommitStatus("COMMITTED");
    } catch (err: any) {
      setActionError(err.message || "Failed to commit changes.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleApprovePush = () => {
    setPushStatus("APPROVED");
  };

  const handlePush = async () => {
    if (!onPush) return;
    setIsActionLoading(true);
    setActionError(null);
    try {
      await onPush(workspace.workspace_id);
      setPushStatus("PUSHED");
    } catch (err: any) {
      setActionError(err.message || "Failed to push branch.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleApprovePR = () => {
    setPrStatus("APPROVED");
  };

  const handleCreatePR = async () => {
    if (!onCreatePR) return;
    setIsActionLoading(true);
    setActionError(null);
    try {
      await onCreatePR(workspace.workspace_id);
      setPrStatus("CREATED");
    } catch (err: any) {
      setActionError(err.message || "Failed to create pull request.");
    } finally {
      setIsActionLoading(false);
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/90 p-4 text-slate-200 shadow-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-violet-950 text-violet-400 text-xs font-bold border border-violet-700/50">
            ⎇
          </span>
          <h4 className="font-semibold text-slate-100 text-sm">
            Git & GitHub Integration (Gates 3, 4, 5)
          </h4>
        </div>
        <div className="flex items-center space-x-2">
          <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-mono text-slate-300 border border-slate-700">
            {workspace.branch_name || `forge/${workspace.session_id.slice(0, 8)}`}
          </span>
        </div>
      </div>

      {/* Metadata Overview */}
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3 text-xs">
        <div className="rounded bg-slate-950/80 p-2.5 border border-slate-800">
          <div className="text-[10px] uppercase font-bold text-slate-400">1. Commit</div>
          <div className="mt-1 font-mono text-slate-200">
            {commit ? (
              <span className="text-emerald-400">✓ {commit.commit_sha.slice(0, 7)}</span>
            ) : commitStatus === "APPROVED" ? (
              <span className="text-blue-400">Approved (Ready)</span>
            ) : (
              <span className="text-slate-400">Pending Gate 3</span>
            )}
          </div>
        </div>

        <div className="rounded bg-slate-950/80 p-2.5 border border-slate-800">
          <div className="text-[10px] uppercase font-bold text-slate-400">2. Remote Push</div>
          <div className="mt-1 font-mono text-slate-200">
            {pushStatus === "PUSHED" ? (
              <span className="text-emerald-400">✓ Pushed</span>
            ) : pushStatus === "APPROVED" ? (
              <span className="text-blue-400">Approved (Ready)</span>
            ) : (
              <span className="text-slate-400">Pending Gate 4</span>
            )}
          </div>
        </div>

        <div className="rounded bg-slate-950/80 p-2.5 border border-slate-800">
          <div className="text-[10px] uppercase font-bold text-slate-400">3. Pull Request</div>
          <div className="mt-1 font-mono text-slate-200">
            {pullRequest ? (
              <a
                href={pullRequest.github_pr_url || "#"}
                target="_blank"
                rel="noreferrer"
                className="text-cyan-400 hover:underline flex items-center gap-1"
              >
                PR #{pullRequest.github_pr_number || 1} ↗
              </a>
            ) : prStatus === "APPROVED" ? (
              <span className="text-blue-400">Approved (Ready)</span>
            ) : (
              <span className="text-slate-400">Pending Gate 5</span>
            )}
          </div>
        </div>
      </div>

      {/* Error message */}
      {actionError && (
        <div className="mt-3 rounded bg-rose-950/60 p-2 text-xs text-rose-300 border border-rose-800">
          {actionError}
        </div>
      )}

      {/* Action Controls */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-3">
        <div className="text-[11px] text-slate-400">
          {pullRequest && (
            <span className="text-emerald-400 font-medium">
              ✓ Pull Request created successfully. Review on GitHub.
            </span>
          )}
          {!pullRequest && pushStatus === "PUSHED" && (
            <span>Branch pushed. Review Gate 5 to create Pull Request.</span>
          )}
          {!pullRequest && pushStatus !== "PUSHED" && commit && (
            <span>Commit recorded. Review Gate 4 to push to remote repository.</span>
          )}
          {!commit && (
            <span>Review Gate 3 to commit approved workspace changes.</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Gate 3: Commit Actions */}
          {commitStatus === "IDLE" && (
            <button
              type="button"
              onClick={handleApproveCommit}
              disabled={isActionLoading}
              className="rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              Approve Commit (Gate 3)
            </button>
          )}
          {commitStatus === "APPROVED" && (
            <button
              type="button"
              onClick={handleCommit}
              disabled={isActionLoading}
              className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
            >
              {isActionLoading ? "Committing..." : "Commit Changes"}
            </button>
          )}

          {/* Gate 4: Push Actions */}
          {commitStatus === "COMMITTED" && pushStatus === "IDLE" && (
            <button
              type="button"
              onClick={handleApprovePush}
              disabled={isActionLoading}
              className="rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              Approve Push (Gate 4)
            </button>
          )}
          {commitStatus === "COMMITTED" && pushStatus === "APPROVED" && (
            <button
              type="button"
              onClick={handlePush}
              disabled={isActionLoading}
              className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
            >
              {isActionLoading ? "Pushing..." : "Push Branch"}
            </button>
          )}

          {/* Gate 5: PR Actions */}
          {pushStatus === "PUSHED" && prStatus === "IDLE" && (
            <button
              type="button"
              onClick={handleApprovePR}
              disabled={isActionLoading}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
            >
              Approve PR (Gate 5)
            </button>
          )}
          {pushStatus === "PUSHED" && prStatus === "APPROVED" && (
            <button
              type="button"
              onClick={handleCreatePR}
              disabled={isActionLoading}
              className="rounded bg-purple-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-purple-500 transition-colors disabled:opacity-50"
            >
              {isActionLoading ? "Creating PR..." : "Create Pull Request"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
