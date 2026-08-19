"use client";

import React, { useState } from "react";
import { AgentSource } from "@/types";
import { FileCode, Tag, Check, Copy, Layers } from "lucide-react";

interface AgentSourcesProps {
  sources: AgentSource[];
}

export function AgentSources({ sources }: AgentSourcesProps) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!sources || sources.length === 0) return null;

  // Deduplicate sources by unique key
  const uniqueSources = sources.filter((item, index, self) => {
    const key = `${item.file_path}:${item.start_line || 0}:${item.end_line || 0}:${item.symbol_name || ""}`;
    return (
      index ===
      self.findIndex(
        (t) =>
          `${t.file_path}:${t.start_line || 0}:${t.end_line || 0}:${t.symbol_name || ""}` === key
      )
    );
  });

  const handleCopyPath = (filePath: string, key: string) => {
    navigator.clipboard.writeText(filePath);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
        <Layers className="h-3.5 w-3.5 text-cyan-400" />
        <span>Grounded Evidence & Sources ({uniqueSources.length})</span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {uniqueSources.map((source) => {
          const key = `${source.file_path}-${source.start_line || 0}-${source.end_line || 0}-${source.symbol_name || ""}`;
          const isCopied = copiedKey === key;

          return (
            <div
              key={key}
              className="group relative flex flex-col justify-between rounded-lg border border-white/10 bg-slate-900/80 p-2.5 transition-all hover:border-cyan-500/40 hover:bg-slate-850"
            >
              <div className="space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <FileCode className="h-3.5 w-3.5 flex-shrink-0 text-cyan-400" />
                    <span
                      title={source.file_path}
                      className="truncate font-mono text-[11px] font-medium text-slate-200"
                    >
                      {source.file_path}
                    </span>
                  </div>
                  <button
                    type="button"
                    aria-label={`Copy file path ${source.file_path}`}
                    onClick={() => handleCopyPath(source.file_path, key)}
                    className="flex-shrink-0 rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-white/10 hover:text-white group-hover:opacity-100"
                  >
                    {isCopied ? (
                      <Check className="h-3 w-3 text-emerald-400" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                  {source.start_line !== null && source.start_line !== undefined && (
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-400">
                      Lines {source.start_line}
                      {source.end_line && source.end_line !== source.start_line
                        ? `–${source.end_line}`
                        : ""}
                    </span>
                  )}
                  {source.symbol_name && (
                    <span className="flex items-center gap-1 rounded bg-cyan-950/60 px-1.5 py-0.5 font-mono text-cyan-300 border border-cyan-500/20">
                      <Tag className="h-2.5 w-2.5" />
                      {source.symbol_name}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
