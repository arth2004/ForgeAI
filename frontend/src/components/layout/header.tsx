"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Moon,
  Sun,
  User,
  Database,
  Radio,
  LogOut,
  Settings as SettingsIcon,
  ChevronDown,
  LogIn,
  UserPlus,
  Building,
  Mail,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export function Header() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const token = typeof window !== "undefined" ? apiClient.getToken() : null;

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiClient.getHealth(),
    refetchInterval: 15000,
    retry: 1,
  });

  const { data: currentUser } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiClient.getMe(),
    enabled: !!token,
    retry: false,
  });

  const isHealthy = health?.status === "ok";

  const handleLogout = () => {
    apiClient.logout();
    queryClient.clear();
    setMenuOpen(false);
    router.push("/login");
  };

  return (
    <header className="h-16 border-b border-border/40 bg-card/40 backdrop-blur-xl px-8 flex items-center justify-between z-40 relative">
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

        {/* User Profile / Auth State */}
        {mounted && (
          token ? (
            <div className="relative pl-2 border-l border-border/40" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen(!menuOpen)}
                className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-secondary/60 transition-colors focus:outline-none"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white text-xs font-semibold shadow-sm flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
                <div className="hidden sm:flex flex-col text-left">
                  <span className="text-xs font-medium text-foreground truncate max-w-[120px]">
                    {currentUser?.full_name || currentUser?.email?.split("@")[0] || "Developer"}
                  </span>
                  <span className="text-[10px] text-muted-foreground">Workspace</span>
                </div>
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground ml-0.5" />
              </button>

              {/* Account Dropdown Menu */}
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-56 rounded-xl border border-border/60 bg-popover/90 backdrop-blur-xl p-2 shadow-2xl z-50 animate-in fade-in-0 zoom-in-95">
                  <div className="px-3 py-2 border-b border-border/40 mb-1">
                    <p className="text-xs font-semibold text-foreground truncate">
                      {currentUser?.full_name || "Developer"}
                    </p>
                    <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 truncate mt-0.5">
                      <Mail className="w-3 h-3 text-sky-400 flex-shrink-0" />
                      <span className="truncate">{currentUser?.email || "developer@forgeai.dev"}</span>
                    </p>
                  </div>

                  <div className="space-y-1">
                    <Link
                      href="/settings"
                      onClick={() => setMenuOpen(false)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
                    >
                      <SettingsIcon className="w-3.5 h-3.5 text-sky-400" />
                      <span>Account Settings</span>
                    </Link>

                    <button
                      type="button"
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-rose-400 hover:bg-rose-500/10 transition-colors text-left"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      <span>Log Out</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 pl-2 border-l border-border/40">
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 bg-secondary/50 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </Link>
              <Link
                href="/register"
                className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 shadow-sm transition-colors"
              >
                <UserPlus className="w-3.5 h-3.5" />
                <span>Register</span>
              </Link>
            </div>
          )
        )}
      </div>
    </header>
  );
}
