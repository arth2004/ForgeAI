"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, Search, Sparkles } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { EvidenceChunk, HybridSearchResponse } from "@/types";

interface RetrievalSandboxProps {
  projectId: string;
}

export function RetrievalSandbox({ projectId }: RetrievalSandboxProps) {
  const [query, setQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [response, setResponse] = useState<HybridSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const sampleQueries = [
    "Authentication and JWT password security",
    "Tree-sitter AST symbol extractor",
    "Hybrid search Reciprocal Rank Fusion",
    "Database migration and pgvector schema",
  ];

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res: HybridSearchResponse = await apiClient.searchHybrid(projectId, searchQuery, undefined, 15);
      setResponse(res);
      // Default state: ALL chunks collapsed
      setExpandedIds(new Set());
    } catch (err: any) {
      setError(err.message || "Failed to execute hybrid search");
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (chunkId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) {
        next.delete(chunkId);
      } else {
        next.add(chunkId);
      }
      return next;
    });
  };

  const expandAll = () => {
    if (response) {
      const allIds = response.results.map((c, i) => c.chunk_id || `chunk-${i}`);
      setExpandedIds(new Set(allIds));
    }
  };

  const collapseAll = () => {
    setExpandedIds(new Set());
  };

  return (
    <div className="space-y-6">
      {/* Search Header and Input */}
      <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 backdrop-blur-md">
        <div className="space-y-1">
          <h3 className="text-lg font-semibold text-white">Hybrid Retrieval Sandbox & Inspector</h3>
          <p className="text-sm text-slate-400">
            Test 3-stage hybrid search combining pgvector HNSW dense vectors, PostgreSQL tsvector / GIN full-text search, and Reciprocal Rank Fusion (RRF).
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSearch(query);
          }}
          className="mt-4 flex gap-3"
        >
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Search code entities, functions, symbols, or concepts (e.g. 'AES encryption cipher')..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-800/80 px-4 py-3 text-sm text-white placeholder-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-6 py-3 text-sm font-medium text-white shadow-lg shadow-cyan-500/20 hover:bg-cyan-500 disabled:opacity-50"
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Searching...</span>
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                <span>Search Codebase</span>
              </>
            )}
          </button>
        </form>

        {/* Sample queries */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400">Try query:</span>
          {sampleQueries.map((sq, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                setQuery(sq);
                handleSearch(sq);
              }}
              className="rounded-lg border border-white/5 bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300 transition-colors hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-300"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Results Feed */}
      {response && (
        <div className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-3">
            <div className="flex items-center gap-3">
              <h4 className="text-sm font-semibold text-white">
                Retrieved Evidence Chunks ({response.total_results})
              </h4>
              <span className="font-mono text-xs text-slate-400">
                Query: &quot;{response.query}&quot;
              </span>
            </div>

            {/* Expand / Collapse All Controls */}
            {response.results.length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={expandAll}
                  className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-700/80 hover:text-white transition-colors"
                >
                  <ChevronsUpDown className="h-3.5 w-3.5 text-cyan-400" />
                  <span>Expand All</span>
                </button>
                <button
                  type="button"
                  onClick={collapseAll}
                  className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-700/80 hover:text-white transition-colors"
                >
                  <ChevronsDownUp className="h-3.5 w-3.5 text-slate-400" />
                  <span>Collapse All</span>
                </button>
              </div>
            )}
          </div>

          {response.results.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-slate-900/40 p-8 text-center text-sm text-slate-400">
              No matching code chunks found for this query.
            </div>
          ) : (
            <div className="space-y-2">
              {response.results.map((chunk: EvidenceChunk, idx: number) => {
                const chunkKey = chunk.chunk_id || `chunk-${idx}`;
                const isExpanded = expandedIds.has(chunkKey);

                return (
                  <div
                    key={chunkKey}
                    className="rounded-xl border border-white/10 bg-slate-900/70 backdrop-blur-md shadow-md transition-all hover:border-cyan-500/30 overflow-hidden"
                  >
                    {/* Collapsed Header / Summary Row */}
                    <button
                      type="button"
                      onClick={() => toggleExpand(chunkKey)}
                      className="w-full flex items-center justify-between gap-3 p-3.5 text-left transition-colors hover:bg-white/[0.02]"
                    >
                      {/* Left: Rank, File, Lines & Symbol/Context */}
                      <div className="flex flex-1 min-w-0 items-center gap-2.5 flex-wrap">
                        <span className="rounded bg-cyan-950 px-2 py-0.5 font-mono text-xs font-semibold text-cyan-300 border border-cyan-800 flex-shrink-0">
                          #{idx + 1}
                        </span>
                        <span className="font-mono text-xs sm:text-sm font-medium text-white truncate">
                          {chunk.file_path}
                        </span>
                        <span className="font-mono text-xs text-slate-400 flex-shrink-0">
                          Lines {chunk.start_line}–{chunk.end_line}
                        </span>
                        {chunk.symbol_name && (
                          <span className="rounded bg-slate-800/80 px-2 py-0.5 font-mono text-[11px] text-cyan-300 border border-white/10 truncate max-w-[200px]">
                            {chunk.symbol_name}
                          </span>
                        )}
                      </div>

                      {/* Right: Scores & Chevron */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {/* RRF score */}
                        <span className="rounded bg-indigo-950/80 px-2 py-0.5 text-[11px] font-mono text-indigo-300 border border-indigo-800/40">
                          RRF {chunk.rrf_score.toFixed(4)}
                        </span>

                        {/* Dense Rank */}
                        {chunk.dense_rank && (
                          <span className="hidden sm:inline-block rounded bg-emerald-950/80 px-1.5 py-0.5 text-[10px] font-mono text-emerald-400 border border-emerald-800/40">
                            Dense #{chunk.dense_rank}
                          </span>
                        )}

                        {/* Sparse Rank */}
                        {chunk.sparse_rank && (
                          <span className="hidden md:inline-block rounded bg-amber-950/80 px-1.5 py-0.5 text-[10px] font-mono text-amber-400 border border-amber-800/40">
                            Sparse #{chunk.sparse_rank}
                          </span>
                        )}

                        {/* Symbol Rank */}
                        {chunk.symbol_rank && (
                          <span className="hidden lg:inline-block rounded bg-pink-950/80 px-1.5 py-0.5 text-[10px] font-mono text-pink-400 border border-pink-800/40">
                            Symbol #{chunk.symbol_rank}
                          </span>
                        )}

                        {/* Chevron Expand Indicator */}
                        <div className="p-1 text-slate-400 hover:text-white transition-colors">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-cyan-400" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </div>
                      </div>
                    </button>

                    {/* Expanded Detail View */}
                    {isExpanded && (
                      <div className="border-t border-white/5 p-4 bg-slate-950/40 space-y-3">
                        {/* Context Header */}
                        {chunk.context_header && (
                          <div className="rounded bg-slate-800/70 px-3 py-1.5 font-mono text-xs text-cyan-300 border border-white/5">
                            {chunk.context_header}
                          </div>
                        )}

                        {/* Code snippet */}
                        <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 font-mono text-xs text-slate-200 leading-relaxed border border-white/5">
                          <code>{chunk.content}</code>
                        </pre>

                        {/* Citation Lineage & Rank Badges Footer */}
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 font-mono pt-1">
                          <div className="flex items-center gap-3">
                            <div>
                              Branch: <span className="text-slate-300">{chunk.branch_name || "main"}</span>
                            </div>
                            <div>
                              Commit:{" "}
                              <span className="text-slate-300">
                                {chunk.commit_sha ? chunk.commit_sha.slice(0, 10) : "-"}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {chunk.dense_rank && (
                              <span className="sm:hidden rounded bg-emerald-950/80 px-1.5 py-0.5 text-[10px] font-mono text-emerald-400 border border-emerald-800/40">
                                Dense #{chunk.dense_rank}
                              </span>
                            )}
                            {chunk.sparse_rank && (
                              <span className="md:hidden rounded bg-amber-950/80 px-1.5 py-0.5 text-[10px] font-mono text-amber-400 border border-amber-800/40">
                                Sparse #{chunk.sparse_rank}
                              </span>
                            )}
                            {chunk.symbol_rank && (
                              <span className="lg:hidden rounded bg-pink-950/80 px-1.5 py-0.5 text-[10px] font-mono text-pink-400 border border-pink-800/40">
                                Symbol #{chunk.symbol_rank}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
