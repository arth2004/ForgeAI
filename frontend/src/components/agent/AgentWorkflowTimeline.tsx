"use client";

import React from "react";
import {
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  MinusCircle,
  Brain,
  Code2,
  CheckSquare,
  ShieldCheck,
  ChevronRight,
} from "lucide-react";
import { AgentWorkflowRoles, RoleStatus } from "@/types";

interface AgentWorkflowTimelineProps {
  roles?: AgentWorkflowRoles | null;
  currentAgent?: string | null;
  iterationCount?: number;
  maxIterations?: number;
  className?: string;
  onSelectRole?: (role: "PLANNER" | "CODER" | "TESTER" | "REVIEWER") => void;
  selectedRole?: string | null;
}

const ROLE_DEFINITIONS: Array<{
  key: "PLANNER" | "CODER" | "TESTER" | "REVIEWER";
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    key: "PLANNER",
    label: "Planner",
    description: "Repository AST & Plan",
    icon: Brain,
  },
  {
    key: "CODER",
    label: "Coder",
    description: "Patch Synthesis & Fixes",
    icon: Code2,
  },
  {
    key: "TESTER",
    label: "Tester",
    description: "Sandboxed Test Suite",
    icon: CheckSquare,
  },
  {
    key: "REVIEWER",
    label: "Reviewer",
    description: "Security & Quality Audit",
    icon: ShieldCheck,
  },
];

function getStatusBadge(status: RoleStatus) {
  switch (status) {
    case "RUNNING":
      return {
        label: "Running",
        icon: Loader2,
        iconClass: "animate-spin text-cyan-400",
        containerClass: "bg-cyan-500/10 border-cyan-500/30 text-cyan-300 ring-1 ring-cyan-500/20",
      };
    case "COMPLETED":
      return {
        label: "Completed",
        icon: CheckCircle2,
        iconClass: "text-emerald-400",
        containerClass: "bg-emerald-500/10 border-emerald-500/30 text-emerald-300",
      };
    case "FAILED":
      return {
        label: "Failed",
        icon: AlertCircle,
        iconClass: "text-rose-400",
        containerClass: "bg-rose-500/10 border-rose-500/30 text-rose-300",
      };
    case "WAITING_APPROVAL":
      return {
        label: "Waiting Approval",
        icon: Clock,
        iconClass: "text-amber-400 animate-pulse",
        containerClass: "bg-amber-500/10 border-amber-500/30 text-amber-300 ring-1 ring-amber-500/20",
      };
    case "SKIPPED":
      return {
        label: "Skipped",
        icon: MinusCircle,
        iconClass: "text-slate-500",
        containerClass: "bg-slate-800/40 border-slate-700/40 text-slate-400",
      };
    case "PENDING":
    default:
      return {
        label: "Pending",
        icon: Clock,
        iconClass: "text-slate-500",
        containerClass: "bg-slate-800/30 border-slate-700/30 text-slate-400",
      };
  }
}

export function AgentWorkflowTimeline({
  roles,
  currentAgent,
  iterationCount = 1,
  maxIterations = 15,
  className = "",
  onSelectRole,
  selectedRole,
}: AgentWorkflowTimelineProps) {
  const defaultRoles: AgentWorkflowRoles = roles || {
    PLANNER: { role: "PLANNER", status: currentAgent === "PLANNER" ? "RUNNING" : "PENDING" },
    CODER: { role: "CODER", status: currentAgent === "CODER" ? "RUNNING" : "PENDING" },
    TESTER: { role: "TESTER", status: currentAgent === "TESTER" ? "RUNNING" : "PENDING" },
    REVIEWER: { role: "REVIEWER", status: currentAgent === "REVIEWER" ? "RUNNING" : "PENDING" },
  };

  return (
    <div
      className={`rounded-xl border border-white/10 bg-slate-900/80 p-3 shadow-md backdrop-blur-md ${className}`}
      data-testid="agent-workflow-timeline"
      aria-label="Multi-Agent Engineering Workflow Timeline"
    >
      <div className="flex items-center justify-between border-b border-white/5 pb-2 text-[11px]">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">Engineering Workflow</span>
          {currentAgent && currentAgent !== "SUPERVISOR" && (
            <span className="flex items-center gap-1 rounded-md bg-cyan-950/80 px-2 py-0.5 text-[10px] font-medium text-cyan-300 border border-cyan-500/30">
              <Loader2 className="h-2.5 w-2.5 animate-spin text-cyan-400" /> Active: {currentAgent}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] text-slate-400">
          <span>
            Iteration <strong className="text-slate-200">{iterationCount}</strong> / {maxIterations}
          </span>
        </div>
      </div>

      <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4">
        {ROLE_DEFINITIONS.map((def, idx) => {
          const roleState = defaultRoles[def.key] || { role: def.key, status: "PENDING" };
          const badge = getStatusBadge(roleState.status);
          const Icon = def.icon;
          const BadgeIcon = badge.icon;
          const isSelected = selectedRole === def.key;

          return (
            <button
              key={def.key}
              type="button"
              onClick={() => onSelectRole?.(def.key)}
              className={`group relative flex flex-col justify-between rounded-lg border p-2 text-left transition-all ${
                isSelected
                  ? "border-cyan-500/80 bg-cyan-950/30 shadow-sm"
                  : "border-white/5 bg-slate-800/30 hover:border-white/15 hover:bg-slate-800/60"
              }`}
              aria-label={`${def.label} stage: ${badge.label}`}
              tabIndex={0}
            >
              <div className="flex items-start justify-between gap-1.5">
                <div className="flex items-center gap-1.5">
                  <div
                    className={`flex h-6 w-6 items-center justify-center rounded-md border ${
                      roleState.status === "RUNNING"
                        ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300"
                        : roleState.status === "COMPLETED"
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                        : roleState.status === "FAILED"
                        ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                        : roleState.status === "WAITING_APPROVAL"
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                        : "border-slate-700 bg-slate-800/80 text-slate-400"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <span className="block text-[11px] font-semibold text-slate-200 group-hover:text-white">
                      {def.label}
                    </span>
                    <span className="block text-[9px] text-slate-400">{def.description}</span>
                  </div>
                </div>

                {idx < ROLE_DEFINITIONS.length - 1 && (
                  <ChevronRight className="hidden h-3 w-3 text-slate-600 sm:block" aria-hidden="true" />
                )}
              </div>

              <div className="mt-2 flex items-center justify-between border-t border-white/5 pt-1.5 text-[10px]">
                <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 border ${badge.containerClass}`}>
                  <BadgeIcon className={`h-2.5 w-2.5 ${badge.iconClass}`} />
                  <span className="font-medium">{badge.label}</span>
                </span>

                {roleState.duration_ms ? (
                  <span className="font-mono text-[9px] text-slate-400">
                    {(roleState.duration_ms / 1000).toFixed(1)}s
                  </span>
                ) : roleState.repair_cycle ? (
                  <span className="font-mono text-[9px] text-amber-300">
                    cycle #{roleState.repair_cycle}
                  </span>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
