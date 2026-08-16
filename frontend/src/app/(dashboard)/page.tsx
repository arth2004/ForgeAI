"use client";

import React, { useState } from "react";
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
  AlertCircle,
  FolderGit2,
  Lock,
  ArrowUpRight,
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
      // Poll for job completion
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

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Title Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Platform Overview
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20">
              Phase 1 Live
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time status of Forge AI core backend, PostgreSQL + pgvector, Redis, and ARQ workers.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetchHealth()}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-lg bg-secondary/80 hover:bg-secondary text-foreground border border-border/50 transition-colors"
          >
            <Activity className="w-3.5 h-3.5 text-sky-400" />
            <span>Refresh Diagnostics</span>
          </button>
        </div>
      </div>

      {/* Grid: Live Diagnostics & Metric Cards */}
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
            <span className="text-[11px] font-mono text-muted-foreground">v{health?.version || "0.1.0"}</span>
          </div>
          <p className="text-xs text-muted-foreground">Async Python 3.12 runtime with REST & SSE</p>
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
            <span className="text-[11px] font-mono text-emerald-400/90">Port 5432</span>
          </div>
          <p className="text-xs text-muted-foreground">SQLAlchemy 2.x async engine with Alembic migrations</p>
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
            <span className="text-[11px] font-mono text-amber-400/90">Async Pool</span>
          </div>
          <p className="text-xs text-muted-foreground">Background tasks for ingestion & async processing</p>
        </div>
      </div>

      {/* Main Content Grid: ARQ Worker Interactive Test & Architecture Verification */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Worker Verification Sandbox */}
        <div className="lg:col-span-2 p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-6">
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

        {/* Right 1 Col: Phase 1 Boundary Scope */}
        <div className="p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-4">
          <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Phase 1 Deliverables</span>
          </h2>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Strict foundational boundaries established. Future phases (Tree-Sitter, embeddings, LangGraph) build on this foundation.
          </p>

          <div className="space-y-2.5 pt-2 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Multi-tenant Schema</span>
              <span className="text-emerald-400 font-mono text-[11px]">Ready (Alembic)</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">pgvector Extension</span>
              <span className="text-emerald-400 font-mono text-[11px]">Enabled</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Auth & JWT Foundation</span>
              <span className="text-emerald-400 font-mono text-[11px]">AES-256-GCM</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border/40">
              <span className="text-foreground font-medium">Docker Orchestration</span>
              <span className="text-emerald-400 font-mono text-[11px]">5 Services</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
