"use client";

import React from "react";
import { ChatMessage } from "@/types";
import { AgentActivity } from "./AgentActivity";
import { AgentSources } from "./AgentSources";
import { AgentPlanView } from "./AgentPlanView";
import { AgentDiffView } from "./AgentDiffView";
import { AgentTestPanel } from "./AgentTestPanel";
import { Sparkles, User, AlertCircle, Loader2 } from "lucide-react";


interface AgentMessageProps {
  message: ChatMessage;
}

export function AgentMessage({ message }: AgentMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex w-full justify-end" data-testid="user-message">
        <div className="flex max-w-[85%] items-start gap-2 sm:max-w-[75%]">
          <div className="rounded-2xl rounded-tr-sm bg-cyan-600 px-4 py-3 text-xs text-white shadow-md">
            <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          </div>
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-slate-800 border border-white/10 text-slate-300">
            <User className="h-4 w-4" />
          </div>
        </div>
      </div>
    );
  }

  // Assistant Message
  const hasToolActivity = message.toolActivities && message.toolActivities.length > 0;
  const isStreaming = message.status === "streaming";
  const isSending = message.status === "sending";

  return (
    <div className="flex w-full justify-start" data-testid="assistant-message">
      <div className="flex max-w-[95%] items-start gap-3 sm:max-w-[85%]">
        <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-cyan-950 border border-cyan-500/30 text-cyan-400 shadow-sm">
          <Sparkles className="h-4 w-4" />
        </div>

        <div className="flex-1 space-y-2 rounded-2xl rounded-tl-sm border border-white/10 bg-slate-900/90 p-4 text-xs text-slate-200 shadow-lg backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-white/5 pb-1.5">
            <div className="flex items-center gap-1.5 font-semibold text-slate-100">
              <span>Forge AI</span>
              {isStreaming && (
                <span className="flex items-center gap-1 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-normal text-cyan-400 border border-cyan-500/20">
                  <Loader2 className="h-2.5 w-2.5 animate-spin" /> Reasoning
                </span>
              )}
            </div>
          </div>

          {/* Tool activity badges */}
          {hasToolActivity && (
            <AgentActivity activities={message.toolActivities!} isStreaming={isStreaming} />
          )}

          {/* Assistant content / loading */}
          {isSending && !message.content && !hasToolActivity && (
            <div className="flex items-center gap-2 py-2 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
              <span>Analyzing question & selecting tools...</span>
            </div>
          )}

          {message.content && (
            <div className="prose prose-invert max-w-none text-xs leading-relaxed text-slate-200">
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          )}

          {/* Phase 5B Implementation Plan Card & Gate 1 Approval */}
          {message.plan && (
            <AgentPlanView
              plan={message.plan}
              approvalId={message.approvalId}
              initialApprovalStatus={message.approvalStatus || "PENDING"}
              initialWorkspace={message.workspace}
            />
          )}

          {/* Phase 5C Proposed Patch Card & Gate 2 DIFF Approval */}
          {message.patch && (
            <AgentDiffView
              patch={message.patch}
            />
          )}

          {/* Phase 5C Sandboxed Test Execution Panel */}
          {message.testExecution && (
            <AgentTestPanel
              testExecution={message.testExecution}
            />
          )}

          {/* Sources Citations */}
          {message.sources && message.sources.length > 0 && (
            <AgentSources sources={message.sources} />
          )}


          {/* Error Banner */}
          {message.status === "error" && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/30 p-3.5 text-xs text-rose-200 shadow-sm space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-rose-300">
                <AlertCircle className="h-4 w-4 flex-shrink-0 text-rose-400" />
                <span>Agent Execution Error</span>
              </div>
              <p className="pl-6 text-[11px] leading-relaxed text-rose-200/90 whitespace-pre-wrap">
                {message.error || "An error occurred during agent reasoning."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

