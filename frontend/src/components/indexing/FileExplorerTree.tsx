"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";
import { RepositoryFile, RepositoryFileDetail } from "@/types";

interface FileExplorerTreeProps {
  projectId: string;
}

export function FileExplorerTree({ projectId }: FileExplorerTreeProps) {
  const [files, setFiles] = useState<RepositoryFile[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<RepositoryFileDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listIndexedFiles(projectId);
      setFiles(data);
    } catch (err) {
      console.error("Failed to load indexed files:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [projectId]);

  const handleSelectFile = async (file: RepositoryFile) => {
    setLoadingDetail(true);
    try {
      const detail = await apiClient.getFileDetail(projectId, file.id);
      setSelectedFile(detail);
    } catch (err) {
      console.error("Failed to load file details:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const filteredFiles = files.filter(
    (f) =>
      f.file_path.toLowerCase().includes(search.toLowerCase()) ||
      f.language.toLowerCase().includes(search.toLowerCase())
  );

  const getLanguageColor = (lang: string) => {
    switch (lang.toLowerCase()) {
      case "python":
        return "text-amber-400 bg-amber-400/10 border-amber-400/20";
      case "typescript":
        return "text-cyan-400 bg-cyan-400/10 border-cyan-400/20";
      case "javascript":
        return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
      case "markdown":
        return "text-sky-400 bg-sky-400/10 border-sky-400/20";
      case "html":
        return "text-orange-400 bg-orange-400/10 border-orange-400/20";
      case "css":
        return "text-blue-400 bg-blue-400/10 border-blue-400/20";
      case "json":
      case "yaml":
        return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
      default:
        return "text-slate-400 bg-slate-400/10 border-slate-400/20";
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* File List / Explorer */}
      <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-md lg:col-span-5">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white">Indexed Files ({files.length})</h3>
          <button
            onClick={fetchFiles}
            className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-white"
            title="Refresh Files"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        <div className="mt-3">
          <input
            type="text"
            placeholder="Filter files or language..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-slate-800/80 px-3.5 py-2 text-sm text-white placeholder-slate-400 focus:border-cyan-500 focus:outline-none"
          />
        </div>

        <div className="mt-4 max-h-[520px] space-y-1.5 overflow-y-auto pr-1">
          {loading ? (
            <div className="py-8 text-center text-sm text-slate-400">Loading files...</div>
          ) : filteredFiles.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-500">No indexed files found.</div>
          ) : (
            filteredFiles.map((file) => (
              <button
                key={file.id}
                onClick={() => handleSelectFile(file)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-xs transition-all ${
                  selectedFile?.id === file.id
                    ? "border border-cyan-500/40 bg-cyan-500/10 text-white"
                    : "border border-transparent hover:bg-white/5 text-slate-300"
                }`}
              >
                <div className="min-w-0 flex-1 pr-2">
                  <div className="truncate font-mono font-medium text-slate-200">{file.file_path}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-400">
                    <span>{(file.size_bytes / 1024).toFixed(1)} KB</span>
                    <span>•</span>
                    <span className="text-cyan-400">{file.chunks_count} chunks</span>
                  </div>
                </div>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase ${getLanguageColor(
                    file.language
                  )}`}
                >
                  {file.language}
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Semantic Chunk Inspector */}
      <div className="rounded-xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-md lg:col-span-7">
        {loadingDetail ? (
          <div className="flex h-96 items-center justify-center text-sm text-slate-400">
            Parsing semantic chunk data...
          </div>
        ) : selectedFile ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div>
                <h4 className="font-mono text-sm font-semibold text-white">{selectedFile.file_path}</h4>
                <p className="text-xs text-slate-400">
                  {selectedFile.chunks.length} AST Semantic Chunks extracted & indexed
                </p>
              </div>
              <span className="rounded bg-slate-800 px-2 py-1 font-mono text-xs text-cyan-400">
                {selectedFile.language}
              </span>
            </div>

            <div className="max-h-[500px] space-y-4 overflow-y-auto pr-1">
              {selectedFile.chunks.map((chunk, idx) => (
                <div
                  key={chunk.chunk_id || idx}
                  className="rounded-lg border border-white/5 bg-slate-800/50 p-3.5"
                >
                  <div className="flex items-center justify-between border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-cyan-950/80 px-2 py-0.5 text-[10px] font-mono font-medium uppercase text-cyan-400 border border-cyan-800/40">
                        {chunk.chunk_type}
                      </span>
                      {chunk.symbol_name && (
                        <span className="font-mono text-xs font-semibold text-white">
                          {chunk.symbol_name}
                        </span>
                      )}
                    </div>
                    <span className="font-mono text-[11px] text-slate-400">
                      Lines {chunk.start_line} – {chunk.end_line}
                    </span>
                  </div>

                  {chunk.context_header && (
                    <div className="mt-2 font-mono text-[11px] text-slate-400 bg-slate-900/60 rounded px-2 py-1">
                      {chunk.context_header}
                    </div>
                  )}

                  <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-3 font-mono text-xs text-slate-200">
                    <code>{chunk.content}</code>
                  </pre>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex h-96 flex-col items-center justify-center text-center text-slate-400">
            <svg className="h-10 w-10 text-slate-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm font-medium">Select a file from the explorer</p>
            <p className="text-xs text-slate-500 mt-1">View Tree-sitter AST nodes, context headers, and semantic chunk boundaries</p>
          </div>
        )}
      </div>
    </div>
  );
}
