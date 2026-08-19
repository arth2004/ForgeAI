export interface IndexingJob {
  job_id: string;
  repository_id: string;
  branch_id: string;
  index_version_id?: string;
  commit_sha: string;
  status: 'pending' | 'acquiring' | 'parsing' | 'embedding' | 'completed' | 'failed';
  total_files: number;
  processed_files: number;
  total_chunks: number;
  embedded_chunks: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface EvidenceChunk {
  chunk_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  symbol_name?: string;
  chunk_type: string;
  context_header: string;
  content: string;
  rrf_score: number;
  dense_rank?: number;
  sparse_rank?: number;
  symbol_rank?: number;
  commit_sha: string;
  branch_name: string;
  index_version_id?: string;
  repository_id?: string;
}

export interface HybridSearchResponse {
  query: string;
  total_results: number;
  results: EvidenceChunk[];
}

export interface RepositoryFile {
  id: string;
  file_path: string;
  file_name: string;
  extension: string;
  language: string;
  size_bytes: number;
  content_hash: string;
  chunks_count: number;
}

export interface RepositoryFileDetail {
  id: string;
  file_path: string;
  file_name: string;
  language: string;
  size_bytes: number;
  content_hash: string;
  chunks: EvidenceChunk[];
}
