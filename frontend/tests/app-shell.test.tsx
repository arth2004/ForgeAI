import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "@/components/layout/sidebar";
import { apiClient } from "@/lib/api-client";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("Frontend App Shell & Navigation", () => {
  it("renders branding and version tag", () => {
    render(<Sidebar />);
    expect(screen.getByText("Forge AI")).toBeInTheDocument();
    expect(screen.getByText("Phase 4 Agent Live")).toBeInTheDocument();
  });

  it("renders core navigation items", () => {
    render(<Sidebar />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders upcoming capabilities preview", () => {
    render(<Sidebar />);
    expect(screen.getByText("PR Reviewer")).toBeInTheDocument();
    expect(screen.getByText("Architecture Visualizer")).toBeInTheDocument();
    expect(screen.getByText("Autonomous Refactor")).toBeInTheDocument();
  });

  it("API client manages token correctly", () => {
    apiClient.setToken("mock-jwt-token-12345");
    expect(apiClient.getToken()).toBe("mock-jwt-token-12345");

    apiClient.logout();
    expect(apiClient.getToken()).toBeNull();
  });
});
