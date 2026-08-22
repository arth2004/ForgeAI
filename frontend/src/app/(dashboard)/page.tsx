"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  Database,
  Layers,
  Play,
  Radio,
  Server,
  Terminal,
  FolderGit2,
  Sparkles,
  Search,
  Code,
  ArrowRight,
  GitBranch,
  GitCommit,
  GitPullRequest,
  ShieldCheck,
  Cpu,
  Lock,
  Boxes,
  FileCode,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function DashboardPage() {
  const [jobResult, setJobResult] = useState<any>(null);

  // Fetch Health Check Status
  const { data: health, isLoading: isHealthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => apiClient.getHealth(),
    refetchInterval: 10000,
  });

  // Fetch Projects List
  const { data: projects, isLoading: isProjectsLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiClient.getProjects(),
    retry: 1,
  });

  // Trigger ARQ Worker Test Job Mutation
  const triggerJobMutation = useMutation({
    mutationFn: async () => {
      const enqueueResp = await apiClient.triggerWorkerTest(`dashboard-ping-${Date.now()}`);
      let attempts = 0;
      while (attempts < 10) {
        await new Promise((r) => setTimeout(r, 800));
        const statusResp = await apiClient.getWorkerJobStatus(enqueueResp.job_id);
        if (statusResp.status === "complete" || statusResp.result) {
          return statusResp;
        }
        attempts++;
      }
      return { job_id: enqueueResp.job_id, status: "queued/in-progress" };
    },
    onSuccess: (data) => {
      setJobResult(data);
    },
  });

  const projectList = Array.isArray(projects) ? projects : [];

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Title Header & Phase 5 Release Badge */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Forge AI
            </h1>
            <span className="text-sm font-medium text-muted-foreground">
              Repository Intelligence → AI Software Engineering
            </span>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-sm">
              Forge AI v0.5.0
            </span>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Controlled AI Software Engineering Agent
            </span>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1.5">
            Controlled software engineering agent operating with strict human-in-the-loop approval gates, ephemeral git worktrees, and sandboxed test execution.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => refetchHealth()}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-lg bg-secondary/80 hover:bg-secondary text-foreground border border-border/50 transition-colors"
          >
            <Activity className="w-3.5 h-3.5 text-sky-400" />
            <span>Diagnostics</span>
          </button>
          <Link
            href="/projects"
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow-md shadow-cyan-500/20 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Launch Agent Workspace</span>
          </Link>
        </div>
      </div>

      {/* PHASE 5 VISUAL LIFECYCLE PIPELINE */}
      <div className="rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-semibold text-foreground tracking-wide">
              Controlled Software Engineering Lifecycle & Safety Boundaries
            </h2>
          </div>
          <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 px-2.5 py-0.5 rounded-full border border-cyan-800/60">
            5 Human Gates Enforced
          </span>
        </div>

        {/* Visual Lifecycle Nodes */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 pt-2">
          {/* 1. Understand */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>1. Understand</span>
              <Search className="w-3.5 h-3.5 text-sky-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">AST + Hybrid Search</p>
            <p className="text-[10px] text-muted-foreground leading-tight">
              Tree-sitter AST & pgvector RRF retrieval.
            </p>
          </div>

          {/* 2. Plan */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>2. Plan</span>
              <FileCode className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">Implementation Plan</p>
            <p className="text-[10px] text-indigo-400 font-mono">
              [Gate 1: PLAN]
            </p>
          </div>

          {/* 3. Workspace & Patch */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>3. Workspace</span>
              <Boxes className="w-3.5 h-3.5 text-purple-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">Isolated Git Tree</p>
            <p className="text-[10px] text-muted-foreground leading-tight">
              Worktree isolation with SHA256 hashing.
            </p>
          </div>

          {/* 4. Diff Review */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>4. Review</span>
              <Code className="w-3.5 h-3.5 text-cyan-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">Unified Diff</p>
            <p className="text-[10px] text-cyan-400 font-mono">
              [Gate 2: DIFF]
            </p>
          </div>

          {/* 5. Sandboxed Test */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>5. Test</span>
              <Cpu className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">Sandboxed Tests</p>
            <p className="text-[10px] text-muted-foreground leading-tight">
              --network=none container quotas.
            </p>
          </div>

          {/* 6. Commit & Push */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>6. Git Ops</span>
              <GitCommit className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">Branch & Commit</p>
            <p className="text-[10px] text-emerald-400 font-mono">
              [Gate 3 & 4]
            </p>
          </div>

          {/* 7. Pull Request */}
          <div className="flex flex-col p-3 rounded-xl bg-secondary/40 border border-border/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
              <span>7. PR</span>
              <GitPullRequest className="w-3.5 h-3.5 text-rose-400" />
            </div>
            <p className="text-xs font-semibold text-foreground">GitHub PR</p>
            <p className="text-[10px] text-rose-400 font-mono">
              [Gate 5: PR]
            </p>
          </div>
        </div>
      </div>

      {/* Grid: Phase 5 Capability Matrix & Security Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Real Project Status Overview */}
        <div className="lg:col-span-2 p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-5">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                <FolderGit2 className="w-4 h-4 text-cyan-400" />
                <span>Connected Projects & Workspaces</span>
              </h2>
              <p className="text-xs text-muted-foreground">
                Repository intelligence state, indexing status, and active agent sessions.
              </p>
            </div>
            <Link
              href="/projects"
              className="text-xs font-medium text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1"
            >
              <span>View All ({projectList.length})</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {isProjectsLoading ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Loading projects...
            </div>
          ) : projectList.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 p-8 text-center space-y-3">
              <FolderGit2 className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">No projects created yet</p>
                <p className="text-xs text-muted-foreground">
                  Connect a GitHub repository or create a workspace project to start.
                </p>
              </div>
              <Link
                href="/projects"
                className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white"
              >
                <span>Create First Project</span>
              </Link>
            </div>
          ) : (
            <div className="space-y-2.5">
              {projectList.slice(0, 4).map((p) => {
                const repo = p.repositories && p.repositories.length > 0 ? p.repositories[0] : null;
                return (
                  <Link
                    key={p.id}
                    href={`/projects/${p.id}`}
                    className="flex items-center justify-between p-3.5 rounded-xl bg-secondary/30 hover:bg-secondary/60 border border-border/40 transition-all group"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground group-hover:text-cyan-300 transition-colors truncate">
                          {p.name}
                        </span>
                        {repo && (
                          <span className="text-[10px] font-mono text-muted-foreground bg-secondary/80 px-2 py-0.5 rounded border border-border/40">
                            {repo.full_name}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground truncate">
                        {p.description || "Active engineering workspace."}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 flex-shrink-0">
                      <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded-full border border-emerald-800/40">
                        Ready
                      </span>
                      <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-cyan-400 group-hover:translate-x-0.5 transition-all" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>

        {/* Right 1 Col: Security & Safety Gate Boundaries */}
        <div className="p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-4">
          <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Lock className="w-4 h-4 text-emerald-400" />
            <span>Security & Guardrails</span>
          </h2>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Forge AI never autonomously mutates remote repositories. All persistent actions require explicit human authentication.
          </p>

          <div className="space-y-2 pt-1 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Gate 1: Implementation Plan</span>
              <span className="text-emerald-400 font-mono text-[11px]">Human Required</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Gate 2: Diff Review & Patch</span>
              <span className="text-emerald-400 font-mono text-[11px]">Human Required</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Gate 3: Local Git Commit</span>
              <span className="text-emerald-400 font-mono text-[11px]">Human Required</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Gate 4: Remote Branch Push</span>
              <span className="text-emerald-400 font-mono text-[11px]">Human Required</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Gate 5: GitHub Pull Request</span>
              <span className="text-emerald-400 font-mono text-[11px]">Human Required</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Protected Branches (main, master)</span>
              <span className="text-amber-400 font-mono text-[11px]">Enforced Block</span>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Core Diagnostics & Infrastructure Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Core API Status */}
        <div className="p-5 rounded-xl border border-border/50 bg-card/60 backdrop-blur-xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              FastAPI Gateway
            </span>
            <Server className="w-4 h-4 text-sky-400" />
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-2xl font-bold text-foreground">
              {health?.status === "ok" ? "Operational" : isHealthLoading ? "Connecting..." : "Degraded"}
            </div>
            <span className="text-[11px] font-mono text-muted-foreground">v{health?.version || "0.5.0"}</span>
          </div>
          <p className="text-xs text-muted-foreground">Async Python 3.12 with REST + SSE Stream</p>
        </div>

        {/* PostgreSQL 16 + pgvector */}
        <div className="p-5 rounded-xl border border-border/50 bg-card/60 backdrop-blur-xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Postgres + pgvector
            </span>
            <Database className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-2xl font-bold text-foreground">
              {health?.services?.database === "ok" ? "Healthy" : "Offline"}
            </div>
            <span className="text-[11px] font-mono text-emerald-400/90">HNSW 768d</span>
          </div>
          <p className="text-xs text-muted-foreground">Vector search, tsvector GIN, and agent sessions</p>
        </div>

        {/* Redis Cache & Queue */}
        <div className="p-5 rounded-xl border border-border/50 bg-card/60 backdrop-blur-xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Redis Broker
            </span>
            <Radio className="w-4 h-4 text-rose-400" />
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-2xl font-bold text-foreground">
              {health?.services?.redis === "ok" ? "Connected" : "Offline"}
            </div>
            <span className="text-[11px] font-mono text-rose-400/90">Port 6379</span>
          </div>
          <p className="text-xs text-muted-foreground">Async Redis pool for rate limits and ARQ queues</p>
        </div>

        {/* ARQ Worker Queue */}
        <div className="p-5 rounded-xl border border-border/50 bg-card/60 backdrop-blur-xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              ARQ Worker Queue
            </span>
            <Layers className="w-4 h-4 text-amber-400" />
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-2xl font-bold text-foreground">
              {health?.services?.worker_queue === "ok" ? "Ready" : "Degraded"}
            </div>
            <span className="text-[11px] font-mono text-amber-400/90">Async Ingest</span>
          </div>
          <p className="text-xs text-muted-foreground">Background jobs for ingestion & embeddings</p>
        </div>
      </div>

      {/* ARQ Worker Verification Sandbox */}
      <div className="p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">
              ARQ Background Pipeline Verification
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Trigger a live task from Next.js → FastAPI → Redis → ARQ Worker → Result.
            </p>
          </div>
          <button
            onClick={() => triggerJobMutation.mutate()}
            disabled={triggerJobMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-sky-500 hover:bg-sky-400 text-white shadow-md shadow-sky-500/20 transition-all disabled:opacity-50"
          >
            {triggerJobMutation.isPending ? (
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current" />
            )}
            <span>{triggerJobMutation.isPending ? "Executing in Worker..." : "Dispatch Test Task"}</span>
          </button>
        </div>

        {/* Execution Result Log Terminal */}
        <div className="p-4 rounded-xl bg-slate-950/80 border border-border/40 font-mono text-xs text-slate-300 space-y-2">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground border-b border-border/30 pb-2">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-sky-400" />
              <span>worker_pipeline_output.json</span>
            </div>
            <span className="text-emerald-400">
              {jobResult ? "Job Completed" : "Ready for execution"}
            </span>
          </div>

          <pre className="overflow-x-auto text-[11px] text-sky-300/90 py-1">
            {jobResult
              ? JSON.stringify(jobResult, null, 2)
              : `{\n  "message": "Click 'Dispatch Test Task' to verify ARQ async job processing",\n  "target_function": "app.workers.health_tasks.health_check_job",\n  "status": "idle"\n}`}
          </pre>
        </div>
      </div>
    </div>
  );
}
