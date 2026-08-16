import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GitHubImportWizard } from "@/components/projects/github-import-wizard";
import { apiClient } from "@/lib/api-client";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

const mockOrgs = [
  {
    id: "org-123",
    name: "Engineering Org",
    slug: "engineering-org",
    created_at: "2026-08-16T12:00:00Z",
    updated_at: "2026-08-16T12:00:00Z",
  },
];

describe("GitHub Import Wizard", () => {
  it("renders wizard step 1 and checks connection status", async () => {
    vi.spyOn(apiClient, "getGitHubStatus").mockResolvedValue({
      is_connected: true,
      github_user_id: 123456,
      github_username: "octocat",
      github_installation_id: 9999,
      avatar_url: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <GitHubImportWizard
          organizations={mockOrgs}
          onSuccess={vi.fn()}
          onCancel={vi.fn()}
        />
      </QueryClientProvider>
    );

    expect(screen.getByText("Import GitHub Repository")).toBeInTheDocument();
    expect(await screen.findByText("@octocat")).toBeInTheDocument();
    expect(screen.getByText("Select Repository")).toBeInTheDocument();
  });

  it("API client correctly exposes GitHub methods", () => {
    expect(typeof apiClient.getGitHubStatus).toBe("function");
    expect(typeof apiClient.getGitHubAuthorizeUrl).toBe("function");
    expect(typeof apiClient.getGitHubRepositories).toBe("function");
    expect(typeof apiClient.getGitHubBranches).toBe("function");
    expect(typeof apiClient.createProjectFromGitHub).toBe("function");
  });
});
