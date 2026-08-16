"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, User, Database, Radio } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiClient.getHealth(),
    refetchInterval: 15000,
    retry: 1,
  });

  const isHealthy = health?.status === "ok";

  return (
    <header className="h-16 border-b border-border/40 bg-card/40 backdrop-blur-xl px-8 flex items-center justify-between">
      {/* Breadcrumb / Title Context */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground bg-secondary/50 px-3 py-1.5 rounded-lg border border-border/40">
          <Database className="w-3.5 h-3.5 text-sky-400" />
          <span>PostgreSQL + pgvector</span>
          <span className="text-border">|</span>
          <Radio className="w-3.5 h-3.5 text-emerald-400" />
          <span>ARQ Worker</span>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-4">
        {/* Health status badge */}
        <div
          className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${
            isHealthy
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-amber-500/10 text-amber-400 border-amber-500/20"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? "bg-emerald-400" : "bg-amber-400"}`} />
          <span>API: {isHealthy ? "Connected" : "Standby / Checking"}</span>
        </div>

        {/* Theme Toggle */}
        {mounted && (
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="p-2 rounded-lg bg-secondary/60 hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors border border-border/40"
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-sky-500" />}
          </button>
        )}

        {/* User Avatar Placeholder */}
        <div className="flex items-center gap-2 pl-2 border-l border-border/40">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white text-xs font-semibold shadow-sm">
            <User className="w-4 h-4" />
          </div>
          <span className="text-xs font-medium text-foreground hidden sm:inline">Developer</span>
        </div>
      </div>
    </header>
  );
}
