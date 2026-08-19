"use client";

import React, { useEffect, useRef } from "react";
import { ChatMessage } from "@/types";
import { AgentMessage } from "./AgentMessage";
import { AgentEmptyState } from "./AgentEmptyState";

interface AgentMessageListProps {
  messages: ChatMessage[];
  onSelectPrompt: (prompt: string) => void;
}

export function AgentMessageList({ messages, onSelectPrompt }: AgentMessageListProps) {
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof scrollEndRef.current?.scrollIntoView === "function") {
      scrollEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  if (!messages || messages.length === 0) {
    return <AgentEmptyState onSelectPrompt={onSelectPrompt} />;
  }

  return (
    <div
      role="log"
      aria-label="Agent Conversation History"
      className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6"
    >
      {messages.map((msg) => (
        <AgentMessage key={msg.id} message={msg} />
      ))}
      <div ref={scrollEndRef} />
    </div>
  );
}
