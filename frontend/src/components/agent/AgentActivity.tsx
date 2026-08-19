"use client";

import React, { useState } from "react";
import { AgentToolActivity } from "@/types";
import { ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Loader2, Wrench, Search, Code, FileText } from "lucide-react";

interface AgentActivityProps {
  activities: AgentToolActivity[];
  isStreaming?: boolean;
}

function getToolDisplay(toolName: string) {
  switch (toolName) {
    case "search_repository":
      return { label: "Searching repository codebase", icon: Search };
    case "search_symbol":
      return { label: "Locating AST symbol declarations", icon: Code };
    case "get_file":
      return { label: "Inspecting file implementation", icon: FileText };
    default:
      return { label: `Running ${toolName}`, icon: Wrench };
  }
}

export function AgentActivity({ activities, isStreaming }: AgentActivityProps) {
  const [isOpen, setIsOpen] = useState(true);

  if (!activities || activities.length === 0) return null;

  const runningCount = activities.filter((a) => a.status === "running").length;
  const completedCount = activities.filter((a) => a.status === "success").length;

  return (
    <div className="my-2 rounded-lg border border-cyan-500/20 bg-slate-900/60 p-2.5 text-xs">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between font-medium text-slate-300 hover:text-white transition-colors"
      >
        <div className="flex items-center gap-2">
          {runningCount > 0 ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          )}
          <span>
            {runningCount > 0
              ? `Reasoning & gathering evidence (${activities.length} tool calls)...`
              : `Tool activity completed (${completedCount} tool actions)`}
          </span>
        </div>
        {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>

      {isOpen && (
        <div className="mt-2.5 space-y-1.5 border-t border-white/5 pt-2">
          {activities.map((act, index) => {
            const { label, icon: Icon } = getToolDisplay(act.tool);
            return (
              <div
                key={act.id || `${act.tool}-${index}`}
                className="flex items-center justify-between rounded bg-slate-800/40 px-2 py-1 text-[11px] text-slate-300"
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-3 w-3 text-cyan-400" />
                  <span>{label}</span>
                </div>
                <div className="flex items-center gap-1.5 font-mono text-[10px]">
                  {act.status === "running" && (
                    <span className="flex items-center gap-1 text-cyan-400">
                      <Loader2 className="h-2.5 w-2.5 animate-spin" /> running
                    </span>
                  )}
                  {act.status === "success" && (
                    <span className="text-emerald-400">
                      ✓ done {act.duration_ms ? `(${act.duration_ms}ms)` : ""}
                    </span>
                  )}
                  {act.status === "failed" && (
                    <span className="flex items-center gap-1 text-rose-400">
                      <AlertCircle className="h-2.5 w-2.5" /> failed
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
