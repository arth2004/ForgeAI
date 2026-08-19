"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Square, Sparkles } from "lucide-react";

interface AgentComposerProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
  isLoading: boolean;
  disabled?: boolean;
}

const MAX_MESSAGE_LENGTH = 4000;

export function AgentComposer({
  onSend,
  onCancel,
  isStreaming,
  isLoading,
  disabled,
}: AgentComposerProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isBusy = isStreaming || isLoading;
  const canSend = text.trim().length > 0 && !isBusy && !disabled;

  useEffect(() => {
    if (!isBusy && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isBusy]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) {
        onSend(text);
        setText("");
      }
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (canSend) {
      onSend(text);
      setText("");
    }
  };

  return (
    <form
      onSubmit={handleFormSubmit}
      className="relative rounded-2xl border border-white/10 bg-slate-900/90 p-3 shadow-xl backdrop-blur-md transition-all focus-within:border-cyan-500/50"
    >
      <div className="relative">
        <textarea
          ref={textareaRef}
          aria-label="Ask Forge AI a question about this repository"
          placeholder="Ask Forge AI about this repository (e.g., 'Where is authentication implemented?')..."
          value={text}
          disabled={disabled}
          maxLength={MAX_MESSAGE_LENGTH}
          rows={2}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-full resize-none bg-transparent px-2 py-1 text-xs text-slate-100 placeholder-slate-500 focus:outline-none disabled:opacity-50"
        />

        <div className="flex items-center justify-between pt-2 border-t border-white/5">
          <div className="flex items-center gap-2 text-[10px] text-slate-500">
            <span className="flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-cyan-400" />
              <span>Grounded reasoning</span>
            </span>
            <span>•</span>
            <span>Enter to send, Shift+Enter for newline</span>
          </div>

          <div className="flex items-center gap-2">
            {text.length > 3000 && (
              <span className="text-[10px] text-slate-500">
                {text.length}/{MAX_MESSAGE_LENGTH}
              </span>
            )}

            {isStreaming ? (
              <button
                type="button"
                aria-label="Cancel agent reasoning"
                onClick={onCancel}
                className="flex items-center gap-1.5 rounded-lg bg-rose-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-rose-500 shadow-sm"
              >
                <Square className="h-3 w-3 fill-current" />
                <span>Stop</span>
              </button>
            ) : (
              <button
                type="submit"
                aria-label="Send message to agent"
                disabled={!canSend}
                className="flex items-center gap-1.5 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white transition-all hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
              >
                <Send className="h-3 w-3" />
                <span>Send</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
