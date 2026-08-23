"use client";

import React, { useState } from "react";
import {
  Brain,
  Code2,
  CheckSquare,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileCode,
  Wrench,
  Clock,
  CheckCircle2,
  AlertCircle,
  ShieldAlert,
} from "lucide-react";
import { AgentRoleState, ImplementationPlan, AgentPatch, AgentTestExecution, AgentReview } from "@/types";

interface AgentRoleCardProps {
  roleState: AgentRoleState;
  plan?: ImplementationPlan | null;
  patch?: AgentPatch | null;
  testExecution?: AgentTestExecution | null;
  review?: AgentReview | null;
  className?: string;
}

export function AgentRoleCard({
  roleState,
  plan,
  patch,
  testExecution,
  review,
  className = "",
}: AgentRoleCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const getRoleIcon = () => {
    switch (roleState.role) {
      case "PLANNER":
        return Brain;
      case "CODER":
        return Code2;
      case "TESTER":
        return CheckSquare;
      case "REVIEWER":
        return ShieldCheck;
    }
  };

  const RoleIcon = getRoleIcon();

  const renderRoleSpecificSummary = () => {
    switch (roleState.role) {
      case "PLANNER":
        return (
          <div className="space-y-1.5 text-xs text-slate-300">
            {plan ? (
              <>
                <div className="font-medium text-slate-100">{plan.summary}</div>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1">
                    <FileCode className="h-3 w-3 text-cyan-400" />
                    {plan.affected_files?.length || 0} affected files
                  </span>
                  <span>•</span>
                  <span>Strategy: {plan.test_strategy || "pytest"}</span>
                </div>
                {isExpanded && plan.affected_files && plan.affected_files.length > 0 && (
                  <div className="mt-2 space-y-1 rounded bg-slate-900/60 p-2 font-mono text-[11px]">
                    <div className="text-[10px] font-sans font-semibold text-slate-400 uppercase tracking-wider">
                      Target Files
                    </div>
                    {plan.affected_files.map((af, i) => (
                      <div key={i} className="flex items-center justify-between text-slate-300">
                        <span>{af.file_path}</span>
                        <span className="text-[10px] text-cyan-400">{af.change_type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="text-slate-400">{roleState.summary || "Investigation and planning in progress..."}</p>
            )}
          </div>
        );

      case "CODER":
        return (
          <div className="space-y-1.5 text-xs text-slate-300">
            {patch ? (
              <>
                <div className="font-medium text-slate-100">{patch.summary || "Structured Patch Proposal"}</div>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1">
                    <FileCode className="h-3 w-3 text-cyan-400" />
                    {patch.files?.length || 0} modified files
                  </span>
                  <span>•</span>
                  <span className="font-mono text-[10px] text-emerald-400">Status: {patch.status}</span>
                </div>
                {isExpanded && patch.files && (
                  <div className="mt-2 space-y-1 rounded bg-slate-900/60 p-2 font-mono text-[11px]">
                    <div className="text-[10px] font-sans font-semibold text-slate-400 uppercase tracking-wider">
                      Patch Files
                    </div>
                    {patch.files.map((pf, i) => (
                      <div key={i} className="flex items-center justify-between text-slate-300">
                        <span>{pf.file_path}</span>
                        <span className="text-[10px] text-amber-400">{pf.operation}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="text-slate-400">{roleState.summary || "Code synthesis and workspace modifications..."}</p>
            )}
          </div>
        );

      case "TESTER":
        return (
          <div className="space-y-1.5 text-xs text-slate-300">
            {testExecution ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-100">
                    Runner: {testExecution.test_command?.runner || "pytest"}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      testExecution.status === "PASSED"
                        ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                        : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
                    }`}
                  >
                    {testExecution.status} (exit {testExecution.exit_code ?? 0})
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1 font-mono">
                    <Clock className="h-3 w-3 text-cyan-400" />
                    {testExecution.duration_ms ? `${testExecution.duration_ms}ms` : "sandboxed"}
                  </span>
                </div>
                {isExpanded && testExecution.stdout && (
                  <div className="mt-2 overflow-x-auto rounded bg-black/50 p-2 font-mono text-[10px] text-slate-300">
                    <pre className="whitespace-pre-wrap">{testExecution.stdout.slice(0, 500)}</pre>
                  </div>
                )}
              </>
            ) : (
              <p className="text-slate-400">{roleState.summary || "Sandboxed test execution verification..."}</p>
            )}
          </div>
        );

      case "REVIEWER":
        const findingsCount = review?.findings?.length || 0;
        const criticalCount = review?.findings?.filter((f) => f.severity === "CRITICAL").length || 0;
        const highCount = review?.findings?.filter((f) => f.severity === "HIGH").length || 0;
        const mediumCount = review?.findings?.filter((f) => f.severity === "MEDIUM").length || 0;

        return (
          <div className="space-y-1.5 text-xs text-slate-300">
            {review ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-100">{review.summary || "Security & Quality Review"}</span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      review.status === "APPROVED"
                        ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-300 border border-amber-500/20"
                    }`}
                  >
                    {review.status}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <span className="text-[11px] text-slate-400">{findingsCount} total findings:</span>
                  {criticalCount > 0 && (
                    <span className="rounded bg-rose-500/20 px-1 py-0.2 text-[10px] font-semibold text-rose-300 border border-rose-500/30">
                      {criticalCount} Critical
                    </span>
                  )}
                  {highCount > 0 && (
                    <span className="rounded bg-amber-500/20 px-1 py-0.2 text-[10px] font-semibold text-amber-300 border border-amber-500/30">
                      {highCount} High
                    </span>
                  )}
                  {mediumCount > 0 && (
                    <span className="rounded bg-blue-500/20 px-1 py-0.2 text-[10px] font-semibold text-blue-300 border border-blue-500/30">
                      {mediumCount} Medium
                    </span>
                  )}
                  {findingsCount === 0 && (
                    <span className="text-[10px] text-emerald-400">0 security risks detected</span>
                  )}
                </div>
              </>
            ) : (
              <p className="text-slate-400">{roleState.summary || "Adversarial security & quality auditing..."}</p>
            )}
          </div>
        );
    }
  };

  return (
    <div
      className={`rounded-lg border border-white/10 bg-slate-800/40 p-3 transition-colors ${className}`}
      data-testid={`agent-role-card-${roleState.role.toLowerCase()}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700/60 border border-white/10 text-cyan-400">
            <RoleIcon className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-100">{roleState.role} Agent</h4>
            <span className="text-[10px] font-mono text-slate-400">Status: {roleState.status}</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
          aria-label={isExpanded ? "Collapse role details" : "Expand role details"}
        >
          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      <div className="mt-2 border-t border-white/5 pt-2">{renderRoleSpecificSummary()}</div>
    </div>
  );
}
