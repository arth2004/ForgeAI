"use client";

import React, { useState } from "react";
import { AgentPatch } from "@/types/agent";

import { apiClient } from "@/lib/api-client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AgentDiffViewProps {
  patch: AgentPatch;
  onApprove?: (patchId: string) => Promise<void>;
  onReject?: (patchId: string) => Promise<void>;
  onApply?: (patchId: string) => Promise<void>;
}

export const AgentDiffView: React.FC<AgentDiffViewProps> = ({
  patch,
  onApprove,
  onReject,
  onApply,
}) => {
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [localStatus, setLocalStatus] = useState(patch.status);

  const handleApprove = async () => {
    setIsActionLoading(true);
    setActionError(null);
    try {
      if (onApprove) {
        await onApprove(patch.patch_id);
      } else if (patch.approval_id) {
        const token = apiClient.getToken() || "";
        const res = await fetch(`${API_BASE_URL}/api/v1/agent/approvals/${patch.approval_id}/approve`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });
        if (!res.ok) {
          throw new Error(`Failed to approve patch: HTTP ${res.status}`);
        }
      }
      setLocalStatus("APPROVED");
    } catch (err: any) {
      setActionError(err.message || "Failed to approve patch.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleReject = async () => {
    setIsActionLoading(true);
    setActionError(null);
    try {
      if (onReject) {
        await onReject(patch.patch_id);
      } else if (patch.approval_id) {
        const token = apiClient.getToken() || "";
        const res = await fetch(`${API_BASE_URL}/api/v1/agent/approvals/${patch.approval_id}/reject`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });
        if (!res.ok) {
          throw new Error(`Failed to reject patch: HTTP ${res.status}`);
        }
      }
      setLocalStatus("REJECTED");
    } catch (err: any) {
      setActionError(err.message || "Failed to reject patch.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleApply = async () => {
    setIsActionLoading(true);
    setActionError(null);
    try {
      if (onApply) {
        await onApply(patch.patch_id);
      } else {
        const token = apiClient.getToken() || "";
        const res = await fetch(`${API_BASE_URL}/api/v1/agent/patches/${patch.patch_id}/apply`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            workspace_id: patch.workspace_id,
            approval_id: patch.approval_id,
          }),
        });
        if (!res.ok) {
          throw new Error(`Failed to apply patch: HTTP ${res.status}`);
        }
      }
      setLocalStatus("APPLIED");
    } catch (err: any) {
      setActionError(err.message || "Failed to apply patch.");
    } finally {
      setIsActionLoading(false);
    }
  };


  const diffLines = (patch.diff_content || "").split("\n");
  const addedCount = diffLines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
  const removedCount = diffLines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/90 p-4 text-slate-200 shadow-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-950 text-cyan-400 text-xs font-bold border border-cyan-700/50">
            Δ
          </span>
          <h4 className="font-semibold text-slate-100 text-sm">
            Proposed Patch Review (Gate 2)
          </h4>
        </div>
        <div className="flex items-center space-x-2">
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
              localStatus === "APPLIED"
                ? "bg-emerald-950 text-emerald-400 border border-emerald-700/50"
                : localStatus === "APPROVED"
                ? "bg-blue-950 text-blue-400 border border-blue-700/50"
                : localStatus === "REJECTED"
                ? "bg-rose-950 text-rose-400 border border-rose-700/50"
                : localStatus === "CONFLICT"
                ? "bg-amber-950 text-amber-400 border border-amber-700/50"
                : "bg-amber-950/80 text-amber-300 border border-amber-700/50 animate-pulse"
            }`}
          >
            {localStatus}
          </span>
        </div>
      </div>

      {/* Summary & Stats */}
      <div className="mt-3 text-xs">
        <p className="text-slate-300 font-medium">{patch.summary}</p>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-slate-400">
          <span>Files changed: <strong className="text-slate-200">{(patch.files || []).length}</strong></span>
          <span className="text-emerald-400 font-medium">+{addedCount} lines</span>
          <span className="text-rose-400 font-medium">-{removedCount} lines</span>
        </div>
      </div>

      {/* Files List */}
      {(patch.files || []).length > 0 && (
        <div className="mt-3 space-y-1">
          {(patch.files || []).map((file, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between rounded bg-slate-950/60 px-2 py-1 text-xs border border-slate-800"
            >
              <span className="font-mono text-slate-300 truncate">{file.file_path}</span>
              <span
                className={`rounded px-1.5 py-0.2 text-[10px] font-bold uppercase ${
                  file.operation === "CREATE"
                    ? "bg-emerald-900/60 text-emerald-300"
                    : file.operation === "DELETE"
                    ? "bg-rose-900/60 text-rose-300"
                    : "bg-blue-900/60 text-blue-300"
                }`}
              >
                {file.operation}
              </span>
            </div>
          ))}
        </div>
      )}


      {/* Unified Diff Box */}
      {patch.diff_content && (
        <div className="mt-3 max-h-64 overflow-y-auto rounded bg-slate-950 p-2 font-mono text-[11px] leading-relaxed border border-slate-800">
          {diffLines.map((line, i) => {
            const isAdd = line.startsWith("+") && !line.startsWith("+++");
            const isDel = line.startsWith("-") && !line.startsWith("---");
            const isHunkHeader = line.startsWith("@@");
            return (
              <div
                key={i}
                className={`px-1 rounded-sm ${
                  isAdd
                    ? "bg-emerald-950/60 text-emerald-300 font-medium"
                    : isDel
                    ? "bg-rose-950/60 text-rose-300 line-through opacity-80"
                    : isHunkHeader
                    ? "bg-indigo-950/50 text-indigo-400 font-semibold my-0.5"
                    : "text-slate-400"
                }`}
              >
                {line || " "}
              </div>
            );
          })}
        </div>
      )}

      {/* Error display */}
      {actionError && (
        <div className="mt-3 rounded bg-rose-950/60 p-2 text-xs text-rose-300 border border-rose-800">
          {actionError}
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-3">
        <div className="text-[11px] text-slate-400">
          {localStatus === "APPLIED" && (
            <span className="text-emerald-400 font-medium">
              ✓ Patch applied atomically to workspace. Ready for testing.
            </span>
          )}
          {localStatus === "APPROVED" && (
            <span className="text-blue-400 font-medium">
              ✓ Diff approved. Click [Apply Patch] to mutate workspace.
            </span>
          )}
          {localStatus === "REJECTED" && (
            <span className="text-rose-400">
              ✕ Patch proposal rejected.
            </span>
          )}
          {localStatus === "AWAITING_APPROVAL" && (
            <span>Review the unified diff before granting approval.</span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {localStatus === "AWAITING_APPROVAL" && (
            <>
              <button
                type="button"
                onClick={handleReject}
                disabled={isActionLoading}
                className="rounded px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-950 border border-rose-700 transition-colors disabled:opacity-50"
              >
                Reject
              </button>
              <button
                type="button"
                onClick={handleApprove}
                disabled={isActionLoading}
                className="rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 shadow-sm transition-colors disabled:opacity-50"
              >
                {isActionLoading ? "Processing..." : "Approve Patch"}
              </button>
            </>
          )}

          {localStatus === "APPROVED" && (
            <button
              type="button"
              onClick={handleApply}
              disabled={isActionLoading}
              className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 shadow-sm transition-colors disabled:opacity-50"
            >
              {isActionLoading ? "Applying..." : "Apply Patch"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
