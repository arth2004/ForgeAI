"use client";

import React, { useState } from "react";
import { ImplementationPlan, AgentWorkspace } from "@/types/agent";
import { CheckCircle, XCircle, FileText, AlertTriangle, ShieldCheck, Cpu, Terminal } from "lucide-react";

import { apiClient } from "@/lib/api-client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AgentPlanViewProps {
  plan: ImplementationPlan;
  approvalId?: string;
  initialApprovalStatus?: string;
  initialWorkspace?: AgentWorkspace | null;
  onApprove?: (approvalId: string) => Promise<void>;
  onReject?: (approvalId: string) => Promise<void>;
}

export const AgentPlanView: React.FC<AgentPlanViewProps> = ({
  plan,
  approvalId,
  initialApprovalStatus = "PENDING",
  initialWorkspace = null,
  onApprove,
  onReject,
}) => {
  const [approvalStatus, setApprovalStatus] = useState<string>(initialApprovalStatus);
  const [workspace, setWorkspace] = useState<AgentWorkspace | null>(initialWorkspace);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleApprove = async () => {
    if (!approvalId) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      if (onApprove) {
        await onApprove(approvalId);
      } else {
        // Direct API call
        const token = apiClient.getToken() || "";
        const approveRes = await fetch(`${API_BASE_URL}/api/v1/agent/approvals/${approvalId}/approve`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });
        if (!approveRes.ok) {
          throw new Error(`Failed to approve plan: HTTP ${approveRes.status}`);
        }

        const approvalData = await approveRes.json();
        setApprovalStatus("APPROVED");

        // Provision isolated workspace
        const wsRes = await fetch(`${API_BASE_URL}/api/v1/agent/workspaces`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            session_id: approvalData.session_id,
            approval_id: approvalId,
          }),
        });

        if (!wsRes.ok) {
          throw new Error(`Failed to create workspace: HTTP ${wsRes.status}`);
        }

        const wsData = await wsRes.json();
        setWorkspace(wsData);
      }
      setApprovalStatus("APPROVED");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to approve plan and provision workspace.");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!approvalId) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      if (onReject) {
        await onReject(approvalId);
      } else {
        const token = apiClient.getToken() || "";
        const rejectRes = await fetch(`${API_BASE_URL}/api/v1/agent/approvals/${approvalId}/reject`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });
        if (!rejectRes.ok) {
          throw new Error(`Failed to reject plan: HTTP ${rejectRes.status}`);
        }
      }
      setApprovalStatus("REJECTED");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to reject plan.");
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="mt-4 border border-zinc-800 bg-zinc-950/80 rounded-xl p-5 shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-4">
        <div className="flex items-center space-x-2">
          <FileText className="w-5 h-5 text-indigo-400" />
          <h3 className="font-semibold text-zinc-100 text-sm tracking-wide">
            Implementation Plan (Gate 1)
          </h3>
        </div>
        <span
          className={`text-xs px-2.5 py-1 rounded-full font-medium ${
            approvalStatus === "APPROVED"
              ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
              : approvalStatus === "REJECTED"
              ? "bg-rose-950 text-rose-300 border border-rose-800/60"
              : "bg-amber-950 text-amber-300 border border-amber-800/60"
          }`}
        >
          {approvalStatus}
        </span>
      </div>

      {/* Summary & Problem */}
      <div className="space-y-3 mb-5">
        <div>
          <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider">Summary</h4>
          <p className="text-sm text-zinc-200 mt-1">{plan.summary}</p>
        </div>

        <div>
          <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider">Problem Statement</h4>
          <p className="text-xs text-zinc-300 mt-1 bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800/80">
            {plan.problem_statement}
          </p>
        </div>

        <div>
          <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider">Approach</h4>
          <p className="text-xs text-zinc-300 mt-1">{plan.approach}</p>
        </div>
      </div>

      {/* Affected Files */}
      {plan.affected_files && plan.affected_files.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider mb-2">
            Affected Files ({plan.affected_files.length})
          </h4>
          <div className="divide-y divide-zinc-800/60 border border-zinc-800/80 rounded-lg overflow-hidden bg-zinc-900/40">
            {plan.affected_files.map((file, idx) => (
              <div key={idx} className="p-3 text-xs flex flex-col space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-zinc-200 font-medium">{file.file_path}</span>
                  <span
                    className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                      file.change_type === "CREATE"
                        ? "bg-blue-900/40 text-blue-300 border border-blue-800/60"
                        : file.change_type === "DELETE"
                        ? "bg-rose-900/40 text-rose-300 border border-rose-800/60"
                        : "bg-amber-900/40 text-amber-300 border border-amber-800/60"
                    }`}
                  >
                    {file.change_type}
                  </span>
                </div>
                <p className="text-zinc-400 text-[11px]">{file.reason}</p>
                {file.symbols && file.symbols.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {file.symbols.map((sym, sIdx) => (
                      <span
                        key={sIdx}
                        className="text-[10px] font-mono bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded"
                      >
                        {sym}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Test Strategy */}
      <div className="mb-4">
        <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider">Test Strategy</h4>
        <p className="text-xs text-zinc-300 mt-1 bg-zinc-900/60 p-2.5 rounded-lg border border-zinc-800/80">
          {plan.test_strategy}
        </p>
      </div>

      {/* Risks */}
      {plan.risks && plan.risks.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs uppercase font-bold text-zinc-400 tracking-wider flex items-center space-x-1 mb-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400 inline" />
            <span>Risks & Edge Cases</span>
          </h4>
          <ul className="list-disc list-inside text-xs text-zinc-300 space-y-1">
            {plan.risks.map((risk, idx) => (
              <li key={idx} className="text-zinc-400">
                {risk}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Error state */}
      {errorMessage && (
        <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800 text-rose-300 text-xs rounded-lg">
          {errorMessage}
        </div>
      )}

      {/* Workspace Status Card if Approved */}
      {approvalStatus === "APPROVED" && (
        <div className="mt-4 p-3.5 bg-emerald-950/40 border border-emerald-800/70 rounded-lg text-xs space-y-2">
          <div className="flex items-center space-x-2 text-emerald-300 font-semibold">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Plan Approved</span>
          </div>
          {workspace ? (
            <div className="space-y-1 text-zinc-300">
              <p className="text-emerald-400 font-medium">Isolated Workspace Ready</p>
              <p className="font-mono text-[11px] text-zinc-400">
                Workspace ID: {workspace.workspace_id}
              </p>
              <p className="font-mono text-[11px] text-zinc-400">
                Base Commit SHA: {workspace.base_commit_sha}
              </p>
              <p className="text-[11px] text-zinc-400 italic">
                Safety Note: No code modifications have occurred.
              </p>
            </div>
          ) : (
            <p className="text-zinc-400 italic">Preparing isolated ephemeral workspace...</p>
          )}
        </div>
      )}

      {/* Rejected State */}
      {approvalStatus === "REJECTED" && (
        <div className="mt-4 p-3 bg-rose-950/40 border border-rose-800/70 rounded-lg text-xs text-rose-300">
          Plan was rejected by reviewer. No workspace or modifications will be created.
        </div>
      )}

      {/* Action Buttons for Pending Plan */}
      {approvalStatus === "PENDING" && (
        <div className="mt-5 pt-3 border-t border-zinc-800 flex items-center justify-end space-x-3">
          <button
            type="button"
            onClick={handleReject}
            disabled={loading}
            className="px-3.5 py-1.5 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors disabled:opacity-50 flex items-center space-x-1.5"
          >
            <XCircle className="w-3.5 h-3.5 text-rose-400" />
            <span>Reject</span>
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={loading}
            className="px-4 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors disabled:opacity-50 flex items-center space-x-1.5 shadow-lg shadow-indigo-500/20"
          >
            <CheckCircle className="w-3.5 h-3.5 text-emerald-300" />
            <span>{loading ? "Preparing isolated workspace..." : "Approve Plan"}</span>
          </button>
        </div>
      )}
    </div>
  );
};
