"use client";

import React from "react";
import {
  GitBranch,
  FolderGit2,
  Cpu,
  Layers,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Shield,
  Activity,
} from "lucide-react";
import { AgentTask } from "@/types";

interface AgentTaskHeaderProps {
  task?: AgentTask | null;
  repositoryName?: string | null;
  branchName?: string | null;
  className?: string;
}

function getLifecycleBadge(state: string) {
  switch (state) {
    case "TASK_CREATED":
    case "INVESTIGATING":
    case "PATCHING":
    case "TESTING":
    case "REVIEWING":
      return {
        label: state.replace("_", " "),
        icon: Loader2,
        iconClass: "animate-spin text-cyan-400",
        containerClass: "bg-cyan-500/10 border-cyan-500/30 text-cyan-300",
      };
    case "PLAN_READY":
    case "PATCH_READY":
    case "WAITING_PLAN_APPROVAL":
    case "WAITING_DIFF_APPROVAL":
    case "WAITING_COMMIT_APPROVAL":
    case "WAITING_PUSH_APPROVAL":
    case "WAITING_PR_APPROVAL":
    case "WAITING_HUMAN_INTERVENTION":
      return {
        label: state.replace(/_/g, " "),
        icon: Clock,
        iconClass: "text-amber-400 animate-pulse",
        containerClass: "bg-amber-500/10 border-amber-500/30 text-amber-300",
      };
    case "COMPLETED":
    case "TEST_PASSED":
    case "REVIEW_PASSED":
      return {
        label: state.replace("_", " "),
        icon: CheckCircle2,
        iconClass: "text-emerald-400",
        containerClass: "bg-emerald-500/10 border-emerald-500/30 text-emerald-300",
      };
    case "FAILED":
    case "TEST_FAILED":
    case "REVIEW_FAILED":
    case "CANCELLED":
      return {
        label: state.replace("_", " "),
        icon: AlertCircle,
        iconClass: "text-rose-400",
        containerClass: "bg-rose-500/10 border-rose-500/30 text-rose-300",
      };
    default:
      return {
        label: state || "UNKNOWN",
        icon: Activity,
        iconClass: "text-slate-400",
        containerClass: "bg-slate-800 border-slate-700 text-slate-300",
      };
  }
}

export function AgentTaskHeader({
  task,
  repositoryName,
  branchName,
  className = "",
}: AgentTaskHeaderProps) {
  if (!task) return null;

  const lifecycleBadge = getLifecycleBadge(task.lifecycle_state);
  const BadgeIcon = lifecycleBadge.icon;
  const maxIterations = 15;
  const iterationPct = Math.min(100, (task.iteration_count / maxIterations) * 100);

  return (
    <div
      className={`rounded-xl border border-white/10 bg-slate-900/90 p-3 shadow-md backdrop-blur-md ${className}`}
      data-testid="agent-task-header"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-xs text-slate-100">{task.title}</span>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border ${lifecycleBadge.containerClass}`}
            >
              <BadgeIcon className={`h-2.5 w-2.5 ${lifecycleBadge.iconClass}`} />
              <span>{lifecycleBadge.label}</span>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
            {repositoryName && (
              <span className="flex items-center gap-1 font-mono text-cyan-300">
                <FolderGit2 className="h-3 w-3 text-slate-500" />
                {repositoryName}
              </span>
            )}
            {branchName && (
              <span className="flex items-center gap-1 font-mono text-slate-300">
                <GitBranch className="h-3 w-3 text-slate-500" />
                {branchName}
              </span>
            )}
            <span className="font-mono text-[10px] text-slate-500">
              Task #{task.id ? task.id.slice(0, 8) : "active"}
            </span>
          </div>
        </div>

        {/* Right side: Active Agent and Iteration budget */}
        <div className="flex items-center gap-3 border-t border-white/5 pt-2 sm:border-t-0 sm:pt-0">
          <div className="flex items-center gap-1.5 rounded-lg bg-slate-800/80 px-2.5 py-1 text-xs border border-white/5">
            <Cpu className="h-3.5 w-3.5 text-cyan-400" />
            <div className="text-[10px]">
              <span className="text-slate-400">Active: </span>
              <strong className="text-slate-200">{task.active_agent || "Supervisor"}</strong>
            </div>
          </div>

          <div className="w-24 space-y-1 text-right text-[10px]">
            <div className="flex justify-between font-mono text-slate-400">
              <span>Budget</span>
              <span className="text-slate-200 font-semibold">
                {task.iteration_count}/{maxIterations}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800 border border-white/5">
              <div
                className={`h-full transition-all duration-300 ${
                  iterationPct > 80 ? "bg-amber-400" : "bg-cyan-500"
                }`}
                style={{ width: `${iterationPct}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
