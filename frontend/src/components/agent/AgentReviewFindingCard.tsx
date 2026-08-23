"use client";

import React, { useState } from "react";
import {
  ShieldAlert,
  AlertTriangle,
  AlertCircle,
  Info,
  ChevronDown,
  ChevronUp,
  FileCode,
  Lightbulb,
  Terminal,
} from "lucide-react";
import { ReviewFinding } from "@/types";

interface AgentReviewFindingCardProps {
  finding: ReviewFinding;
  className?: string;
  defaultExpanded?: boolean;
}

export function getSeverityStyle(severity: ReviewFinding["severity"]) {
  switch (severity) {
    case "CRITICAL":
      return {
        label: "Critical",
        icon: ShieldAlert,
        badgeClass: "bg-rose-500/20 text-rose-300 border-rose-500/40 ring-1 ring-rose-500/30",
        indicatorClass: "text-rose-400",
        borderClass: "border-l-rose-500",
      };
    case "HIGH":
      return {
        label: "High",
        icon: AlertTriangle,
        badgeClass: "bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/20",
        indicatorClass: "text-amber-400",
        borderClass: "border-l-amber-500",
      };
    case "MEDIUM":
      return {
        label: "Medium",
        icon: AlertCircle,
        badgeClass: "bg-yellow-500/10 text-yellow-300 border-yellow-500/30",
        indicatorClass: "text-yellow-400",
        borderClass: "border-l-yellow-500",
      };
    case "LOW":
      return {
        label: "Low",
        icon: Info,
        badgeClass: "bg-blue-500/10 text-blue-300 border-blue-500/30",
        indicatorClass: "text-blue-400",
        borderClass: "border-l-blue-500",
      };
    case "INFO":
    default:
      return {
        label: "Info",
        icon: Info,
        badgeClass: "bg-slate-700/40 text-slate-300 border-slate-600/30",
        indicatorClass: "text-slate-400",
        borderClass: "border-l-slate-500",
      };
  }
}

export function AgentReviewFindingCard({
  finding,
  className = "",
  defaultExpanded = false,
}: AgentReviewFindingCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const severityStyle = getSeverityStyle(finding.severity);
  const SeverityIcon = severityStyle.icon;

  const lineRangeText =
    finding.start_line !== undefined && finding.start_line !== null
      ? finding.end_line && finding.end_line !== finding.start_line
        ? `L${finding.start_line}-${finding.end_line}`
        : `L${finding.start_line}`
      : null;

  return (
    <div
      className={`rounded-lg border border-white/10 bg-slate-900/60 p-3 shadow-sm border-l-4 ${severityStyle.borderClass} ${className}`}
      data-testid="agent-review-finding-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${severityStyle.badgeClass}`}
              aria-label={`Severity: ${severityStyle.label}`}
            >
              <SeverityIcon className={`h-3 w-3 ${severityStyle.indicatorClass}`} aria-hidden="true" />
              {severityStyle.label}
            </span>

            {finding.category && (
              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-300 border border-white/5">
                {finding.category}
              </span>
            )}

            <div className="flex items-center gap-1 font-mono text-[11px] text-cyan-300">
              <FileCode className="h-3 w-3 text-slate-400" />
              <span>{finding.file_path}</span>
              {lineRangeText && <span className="text-slate-400">:{lineRangeText}</span>}
            </div>
          </div>

          <p className="text-xs leading-relaxed text-slate-200">{finding.description}</p>
        </div>

        {(finding.evidence || finding.recommendation) && (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            aria-label={isExpanded ? "Collapse finding details" : "Expand finding details"}
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        )}
      </div>

      {isExpanded && (
        <div className="mt-3 space-y-2 border-t border-white/5 pt-2.5 text-xs">
          {finding.evidence && (
            <div className="rounded-md bg-black/40 p-2 font-mono text-[11px] text-slate-300 border border-white/5">
              <div className="flex items-center gap-1.5 text-[10px] font-sans font-semibold text-slate-400 mb-1">
                <Terminal className="h-3 w-3 text-cyan-400" />
                Code Evidence
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap">{finding.evidence}</pre>
            </div>
          )}

          {finding.recommendation && (
            <div className="rounded-md bg-cyan-950/20 p-2 text-cyan-200 border border-cyan-500/20">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold text-cyan-400 mb-0.5">
                <Lightbulb className="h-3 w-3" />
                Remediation Guidance
              </div>
              <p className="text-[11px] leading-relaxed text-cyan-100/90">{finding.recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
