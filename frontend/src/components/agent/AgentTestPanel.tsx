"use client";

import React from "react";
import { AgentTestExecution } from "@/types/agent";

interface AgentTestPanelProps {
  testExecution: AgentTestExecution;
}

export const AgentTestPanel: React.FC<AgentTestPanelProps> = ({ testExecution }) => {
  const { test_command, status, exit_code, stdout, stderr, duration_ms } = testExecution;

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/90 p-4 text-slate-200 shadow-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-950 text-indigo-400 text-xs font-bold border border-indigo-700/50">
            🧪
          </span>
          <h4 className="font-semibold text-slate-100 text-sm">
            Sandboxed Test Execution
          </h4>
        </div>
        <div className="flex items-center space-x-2">
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
              status === "PASSED"
                ? "bg-emerald-950 text-emerald-400 border border-emerald-700/50"
                : status === "FAILED"
                ? "bg-rose-950 text-rose-400 border border-rose-700/50"
                : status === "RUNNING"
                ? "bg-amber-950 text-amber-300 border border-amber-700/50 animate-pulse"
                : status === "TIMEOUT"
                ? "bg-orange-950 text-orange-400 border border-orange-700/50"
                : "bg-slate-800 text-slate-400 border border-slate-700"
            }`}
          >
            {status}
          </span>
        </div>
      </div>

      {/* Command & Metadata */}
      <div className="mt-3 space-y-1 text-xs">
        <div className="flex items-center space-x-2 font-mono text-slate-300 bg-slate-950/80 px-2.5 py-1.5 rounded border border-slate-800">
          <span className="text-indigo-400 font-bold">$ {test_command?.runner || (testExecution as any).runner || "pytest"}</span>
          <span>{test_command?.arguments?.join(" ") || (Array.isArray((testExecution as any).command) ? (testExecution as any).command.slice(1).join(" ") : "-v")}</span>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-slate-400 pt-1">

          {exit_code !== undefined && exit_code !== null && (
            <span>
              Exit code: <strong className={exit_code === 0 ? "text-emerald-400" : "text-rose-400"}>{exit_code}</strong>
            </span>
          )}
          {duration_ms !== undefined && duration_ms !== null && (
            <span>
              Duration: <strong className="text-slate-200">{duration_ms} ms</strong>
            </span>
          )}
          <span className="text-[11px] text-slate-500">Isolation: --network=none, 2 vCPU, 2048 MB</span>
        </div>
      </div>

      {/* Output Logs */}
      {(stdout || stderr) && (
        <div className="mt-3 space-y-2">
          {stdout && (
            <div>
              <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">STDOUT</div>
              <pre className="max-h-48 overflow-y-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-300 border border-slate-800 whitespace-pre-wrap">
                {stdout}
              </pre>
            </div>
          )}
          {stderr && (
            <div>
              <div className="text-[10px] uppercase font-bold text-rose-400 mb-1">STDERR</div>
              <pre className="max-h-48 overflow-y-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-rose-300 border border-rose-900/60 whitespace-pre-wrap">
                {stderr}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
