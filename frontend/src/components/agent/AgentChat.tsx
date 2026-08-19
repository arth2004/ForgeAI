"use client";

import React from "react";
import { useAgentChat } from "@/hooks/useAgentChat";
import { AgentMessageList } from "./AgentMessageList";
import { AgentComposer } from "./AgentComposer";
import { Sparkles, Trash2, GitBranch, FolderGit2, AlertTriangle } from "lucide-react";

interface AgentChatProps {
  projectId: string;
  repositoryId?: string | null;
  repositoryName?: string;
  branchName?: string;
  branchId?: string | null;
}

export function AgentChat({
  projectId,
  repositoryId,
  repositoryName,
  branchName,
  branchId,
}: AgentChatProps) {
  const {
    messages,
    sessionId,
    isStreaming,
    isLoading,
    error,
    sendMessage,
    cancelStream,
    clearMessages,
  } = useAgentChat({
    projectId,
    repositoryId,
    branchId,
  });

  return (
    <div
      className="flex h-[680px] w-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/60 shadow-2xl backdrop-blur-xl"
      data-testid="agent-chat-container"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 bg-slate-900/60 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-semibold text-white">Forge AI Repository Reasoning Agent</h2>
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400 border border-emerald-500/20">
                Phase 4 Ready
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              {repositoryName && (
                <span className="flex items-center gap-1">
                  <FolderGit2 className="h-3 w-3 text-slate-400" />
                  <span>{repositoryName}</span>
                </span>
              )}
              {branchName && (
                <>
                  <span>•</span>
                  <span className="flex items-center gap-1 font-mono">
                    <GitBranch className="h-3 w-3 text-slate-400" />
                    <span>{branchName}</span>
                  </span>
                </>
              )}
              {sessionId && (
                <>
                  <span>•</span>
                  <span className="font-mono text-[10px] text-slate-500">
                    session: {sessionId.slice(0, 8)}...
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {messages.length > 0 && (
          <button
            type="button"
            aria-label="Clear chat conversation"
            onClick={clearMessages}
            disabled={isStreaming}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-800/60 px-2.5 py-1.5 text-xs text-slate-300 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </button>
        )}
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="flex items-center gap-2 border-b border-rose-500/20 bg-rose-950/40 px-4 py-2 text-xs text-rose-300">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Message List / Empty State */}
      <AgentMessageList
        messages={messages}
        onSelectPrompt={(prompt) => sendMessage(prompt, true)}
      />

      {/* Composer */}
      <div className="p-3 sm:p-4 border-t border-white/5 bg-slate-900/40">
        <AgentComposer
          onSend={(msg) => sendMessage(msg, true)}
          onCancel={cancelStream}
          isStreaming={isStreaming}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
