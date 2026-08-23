"use client";

import React, { useState, useMemo } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Filter,
  CheckCircle2,
  AlertTriangle,
  FolderGit2,
  Layers,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { AgentReview, ReviewFinding } from "@/types";
import { AgentReviewFindingCard } from "./AgentReviewFindingCard";

interface AgentReviewFindingsProps {
  review?: AgentReview | null;
  findings?: ReviewFinding[] | null;
  className?: string;
}

type SeverityFilter = "ALL" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

export function AgentReviewFindings({
  review,
  findings: externalFindings,
  className = "",
}: AgentReviewFindingsProps) {
  const allFindings = useMemo(() => {
    return review?.findings || externalFindings || [];
  }, [review, externalFindings]);

  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("ALL");
  const [groupByFile, setGroupByFile] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const counts = useMemo(() => {
    return {
      TOTAL: allFindings.length,
      CRITICAL: allFindings.filter((f) => f.severity === "CRITICAL").length,
      HIGH: allFindings.filter((f) => f.severity === "HIGH").length,
      MEDIUM: allFindings.filter((f) => f.severity === "MEDIUM").length,
      LOW: allFindings.filter((f) => f.severity === "LOW").length,
      INFO: allFindings.filter((f) => f.severity === "INFO").length,
    };
  }, [allFindings]);

  const filteredFindings = useMemo(() => {
    if (severityFilter === "ALL") return allFindings;
    return allFindings.filter((f) => f.severity === severityFilter);
  }, [allFindings, severityFilter]);

  const groupedByFile = useMemo(() => {
    const groups: Record<string, ReviewFinding[]> = {};
    filteredFindings.forEach((finding) => {
      const file = finding.file_path;
      if (!groups[file]) groups[file] = [];
      groups[file].push(finding);
    });
    return groups;
  }, [filteredFindings]);

  const isApproved = review?.status === "APPROVED" || allFindings.length === 0;

  return (
    <div
      className={`rounded-xl border border-white/10 bg-slate-900/80 p-3.5 shadow-md backdrop-blur-md ${className}`}
      data-testid="agent-review-findings-panel"
      aria-label="Code Review Audit Findings"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div
            className={`flex h-6 w-6 items-center justify-center rounded-md border ${
              isApproved
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/40 bg-amber-500/10 text-amber-300"
            }`}
          >
            {isApproved ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
          </div>
          <div>
            <h3 className="text-xs font-semibold text-slate-100">Reviewer Security & Quality Audit</h3>
            <p className="text-[10px] text-slate-400">
              {review?.summary || (isApproved ? "Patch passed review analysis" : "Reviewer findings require attention")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
              isApproved
                ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                : "bg-amber-500/10 text-amber-300 border-amber-500/30"
            }`}
          >
            {review?.status || (isApproved ? "APPROVED" : "CHANGES_REQUESTED")}
          </span>

          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            aria-label={isCollapsed ? "Expand review panel" : "Collapse review panel"}
          >
            {isCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="mt-3 space-y-3">
          {/* Severity Badges & Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2 text-xs">
            <div className="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Filter findings by severity">
              {(["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"] as SeverityFilter[]).map((sev) => {
                const count = sev === "ALL" ? counts.TOTAL : counts[sev];
                const isActive = severityFilter === sev;
                return (
                  <button
                    key={sev}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setSeverityFilter(sev)}
                    className={`rounded-md px-2 py-1 text-[11px] font-medium transition-all ${
                      isActive
                        ? "bg-cyan-600 text-white shadow-sm"
                        : "bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    }`}
                  >
                    {sev === "ALL" ? "All" : sev.charAt(0) + sev.slice(1).toLowerCase()} ({count})
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setGroupByFile(!groupByFile)}
                className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] border transition-colors ${
                  groupByFile
                    ? "border-cyan-500/40 bg-cyan-950/40 text-cyan-300"
                    : "border-white/10 bg-slate-800/40 text-slate-400 hover:text-slate-200"
                }`}
                aria-pressed={groupByFile}
              >
                <FolderGit2 className="h-3 w-3" />
                Group by File
              </button>
            </div>
          </div>

          {/* Findings List */}
          {allFindings.length === 0 ? (
            <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-3 text-xs text-emerald-300">
              <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-400" />
              <span>Clean review: No critical, security, or regression findings detected.</span>
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="rounded-lg border border-white/5 bg-slate-800/30 p-3 text-center text-xs text-slate-400">
              No findings matching selected severity filter ({severityFilter}).
            </div>
          ) : groupByFile ? (
            <div className="space-y-3">
              {Object.entries(groupedByFile).map(([filePath, fileFindings]) => (
                <div key={filePath} className="rounded-lg border border-white/5 bg-slate-900/40 p-2.5 space-y-2">
                  <div className="flex items-center gap-1.5 font-mono text-xs font-semibold text-slate-300">
                    <FolderGit2 className="h-3.5 w-3.5 text-cyan-400" />
                    <span>{filePath}</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      ({fileFindings.length} {fileFindings.length === 1 ? "finding" : "findings"})
                    </span>
                  </div>
                  <div className="space-y-2 pl-2">
                    {fileFindings.map((finding) => (
                      <AgentReviewFindingCard key={finding.id} finding={finding} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredFindings.map((finding) => (
                <AgentReviewFindingCard key={finding.id} finding={finding} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
