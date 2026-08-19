import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RetrievalSandbox } from "@/components/indexing/RetrievalSandbox";
import { apiClient } from "@/lib/api-client";
import { HybridSearchResponse } from "@/types";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/projects/test-project",
  useRouter: () => ({
    push: vi.fn(),
  }),
  useParams: () => ({ id: "test-project" }),
}));

describe("RetrievalSandbox Collapsible Evidence Chunks", () => {
  const mockSearchResponse: HybridSearchResponse = {
    query: "authentication tokens",
    total_results: 2,
    results: [
      {
        chunk_id: "chunk-1",
        file_path: "src/auth/jwt.py",
        chunk_type: "function",
        start_line: 10,
        end_line: 45,
        content: "def verify_jwt_token(token: str) -> bool:\n    return True",
        context_header: "# File: src/auth/jwt.py | Module: auth",
        symbol_name: "verify_jwt_token",
        dense_rank: 1,
        sparse_rank: 2,
        symbol_rank: 3,
        rrf_score: 0.0452,
        branch_name: "main",
        commit_sha: "abc123456789",
      },
      {
        chunk_id: "chunk-2",
        file_path: "src/auth/middleware.py",
        chunk_type: "class",
        start_line: 5,
        end_line: 25,
        content: "class AuthMiddleware:\n    def process_request(self):\n        pass",
        context_header: "# File: src/auth/middleware.py",
        symbol_name: "AuthMiddleware",
        dense_rank: 2,
        sparse_rank: 1,
        symbol_rank: undefined,
        rrf_score: 0.0418,
        branch_name: "main",
        commit_sha: "abc123456789",
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders search input and triggers hybrid search", async () => {
    vi.spyOn(apiClient, "searchHybrid").mockResolvedValue(mockSearchResponse);

    render(<RetrievalSandbox projectId="test-project" />);

    const input = screen.getByPlaceholderText(/Search code entities/i);
    const searchBtn = screen.getByRole("button", { name: /Search Codebase/i });

    fireEvent.change(input, { target: { value: "authentication tokens" } });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(screen.getByText("Retrieved Evidence Chunks (2)")).toBeInTheDocument();
    });

    // 1. DEFAULT STATE: Results are COLLAPSED (code snippet text is not visible)
    expect(screen.queryByText(/def verify_jwt_token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/class AuthMiddleware/i)).not.toBeInTheDocument();

    // Summary headers are visible
    expect(screen.getByText("src/auth/jwt.py")).toBeInTheDocument();
    expect(screen.getByText("src/auth/middleware.py")).toBeInTheDocument();
    expect(screen.getByText("RRF 0.0452")).toBeInTheDocument();
  });

  it("expands an individual chunk when clicked and collapses on second click", async () => {
    vi.spyOn(apiClient, "searchHybrid").mockResolvedValue(mockSearchResponse);

    render(<RetrievalSandbox projectId="test-project" />);
    const input = screen.getByPlaceholderText(/Search code entities/i);
    fireEvent.change(input, { target: { value: "authentication tokens" } });
    fireEvent.click(screen.getByRole("button", { name: /Search Codebase/i }));

    await waitFor(() => {
      expect(screen.getByText("src/auth/jwt.py")).toBeInTheDocument();
    });

    // Click on chunk 1 row to expand
    const chunk1Row = screen.getByText("src/auth/jwt.py").closest("button")!;
    fireEvent.click(chunk1Row);

    // Now chunk 1 code content is visible
    expect(screen.getByText(/def verify_jwt_token/i)).toBeInTheDocument();
    // Chunk 2 code remains collapsed
    expect(screen.queryByText(/class AuthMiddleware/i)).not.toBeInTheDocument();

    // Click chunk 1 again to collapse
    fireEvent.click(chunk1Row);
    expect(screen.queryByText(/def verify_jwt_token/i)).not.toBeInTheDocument();
  });

  it("handles Expand All and Collapse All buttons correctly", async () => {
    vi.spyOn(apiClient, "searchHybrid").mockResolvedValue(mockSearchResponse);

    render(<RetrievalSandbox projectId="test-project" />);
    const input = screen.getByPlaceholderText(/Search code entities/i);
    fireEvent.change(input, { target: { value: "authentication tokens" } });
    fireEvent.click(screen.getByRole("button", { name: /Search Codebase/i }));

    await waitFor(() => {
      expect(screen.getByText("Expand All")).toBeInTheDocument();
    });

    // Click Expand All
    fireEvent.click(screen.getByText("Expand All"));
    expect(screen.getByText(/def verify_jwt_token/i)).toBeInTheDocument();
    expect(screen.getByText(/class AuthMiddleware/i)).toBeInTheDocument();

    // Click Collapse All
    fireEvent.click(screen.getByText("Collapse All"));
    expect(screen.queryByText(/def verify_jwt_token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/class AuthMiddleware/i)).not.toBeInTheDocument();
  });
});
