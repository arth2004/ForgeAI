"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderGit2,
  Settings,
  Terminal,
  Activity,
  Layers,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigationItems = [
  {
    name: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
  },
  {
    name: "Projects",
    href: "/projects",
    icon: FolderGit2,
  },
  {
    name: "Settings",
    href: "/settings",
    icon: Settings,
  },
];

const futurePhaseFeatures = [
  { name: "Code Assistant", phase: "Phase 4" },
  { name: "PR Reviewer", phase: "Phase 6" },
  { name: "Architecture Map", phase: "Phase 6" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-border/40 bg-card/60 backdrop-blur-xl flex flex-col h-screen select-none">
      {/* Brand Header */}
      <div className="h-16 px-6 flex items-center gap-3 border-b border-border/40">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 via-sky-500 to-indigo-500 flex items-center justify-center shadow-lg shadow-sky-500/20">
          <Terminal className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-base tracking-tight bg-gradient-to-r from-foreground via-foreground to-sky-400 bg-clip-text text-transparent">
              Forge AI
            </span>
            <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
              v0.1
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground font-medium">Phase 1 Foundation</p>
        </div>
      </div>

      {/* Main Navigation */}
      <div className="flex-1 py-6 px-3 space-y-6 overflow-y-auto">
        <div className="space-y-1">
          <div className="px-3 pb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
            Platform
          </div>
          {navigationItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group",
                  isActive
                    ? "bg-sky-500/10 text-sky-400 font-semibold border border-sky-500/20 shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 transition-colors",
                    isActive ? "text-sky-400" : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                <span className="flex-1">{item.name}</span>
                {isActive && <ChevronRight className="w-3.5 h-3.5 text-sky-400/80" />}
              </Link>
            );
          })}
        </div>

        {/* Roadmap Preview */}
        <div className="space-y-2 pt-2 border-t border-border/30">
          <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-sky-400" />
            <span>Upcoming Capabilities</span>
          </div>
          <div className="space-y-1">
            {futurePhaseFeatures.map((feat) => (
              <div
                key={feat.name}
                className="flex items-center justify-between px-3 py-2 text-xs text-muted-foreground/50 rounded-lg cursor-not-allowed select-none"
              >
                <span>{feat.name}</span>
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-secondary/50 border border-border/40">
                  {feat.phase}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* System Status Pill Footer */}
      <div className="p-4 border-t border-border/40 bg-card/20">
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-sky-950/30 border border-sky-500/20 text-xs">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <div className="flex-1 text-[11px]">
            <span className="text-foreground font-medium">Core Stack</span>:{" "}
            <span className="text-emerald-400 font-medium">Active</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
