"use client";

import React from "react";
import { Sparkles, ArrowRight, ShieldCheck, Compass, GitMerge, FileCode } from "lucide-react";

interface AgentEmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
}

const SAMPLE_PROMPTS = [
  {
    title: "Authentication & Security",
    prompt: "Where is JWT authentication and password hashing implemented?",
    icon: ShieldCheck,
    color: "text-emerald-400 border-emerald-500/20 bg-emerald-950/20",
  },
  {
    title: "Hybrid Retrieval Engine",
    prompt: "How does the hybrid retrieval engine combine dense vector and sparse keyword search?",
    icon: Compass,
    color: "text-cyan-400 border-cyan-500/20 bg-cyan-950/20",
  },
  {
    title: "Incremental Indexing",
    prompt: "How does incremental indexing detect changed files between Git commits?",
    icon: GitMerge,
    color: "text-indigo-400 border-indigo-500/20 bg-indigo-950/20",
  },
  {
    title: "AST Parser Framework",
    prompt: "Which Tree-sitter parsers are supported and where is chunking implemented?",
    icon: FileCode,
    color: "text-purple-400 border-purple-500/20 bg-purple-950/20",
  },
];

export function AgentEmptyState({ onSelectPrompt }: AgentEmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-6 text-center animate-in fade-in-50">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-lg shadow-cyan-500/5">
        <Sparkles className="h-6 w-6" />
      </div>

      <h3 className="mt-4 text-base font-semibold text-white">
        Ask Forge AI about this Repository
      </h3>
      <p className="mt-1 max-w-md text-xs text-slate-400">
        Reason over codebase architecture, inspect specific symbol implementations, or locate features using grounded repository intelligence.
      </p>

      <div className="mt-6 grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2 text-left">
        {SAMPLE_PROMPTS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.title}
              type="button"
              onClick={() => onSelectPrompt(item.prompt)}
              className="group flex flex-col justify-between rounded-xl border border-white/10 bg-slate-900/60 p-3.5 text-xs transition-all hover:border-cyan-500/40 hover:bg-slate-800/80 hover:shadow-md"
            >
              <div className="flex items-center gap-2 font-medium text-slate-200">
                <div className={`flex h-6 w-6 items-center justify-center rounded-lg border ${item.color}`}>
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <span>{item.title}</span>
              </div>
              <p className="mt-2 text-[11px] text-slate-400 group-hover:text-slate-300 transition-colors">
                {item.prompt}
              </p>
              <div className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <span>Ask this</span>
                <ArrowRight className="h-3 w-3" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
