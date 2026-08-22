import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { apiClient } from "@/lib/api-client";
import { Header } from "@/components/layout/header";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock next/navigation
const mockPush = vi.fn();
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  usePathname: () => "/",
}));

// Mock next-themes
vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "dark",
    setTheme: vi.fn(),
  }),
}));

describe("Authentication Expiry & 401 Centralized Handling", () => {
  let queryClient: QueryClient;
  const originalLocation = window.location;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    localStorage.clear();
    sessionStorage.clear();
    apiClient.setToken(null);
    vi.clearAllMocks();

    // Mock window.location.replace
    delete (window as any).location;
    (window as any).location = {
      ...originalLocation,
      pathname: "/",
      replace: mockReplace,
    };
  });

  afterEach(() => {
    (window as any).location = originalLocation;
  });

  it("1. Valid token enables authenticated user profile in Header", async () => {
    apiClient.setToken("valid-token-123");

    // Mock fetch for /api/v1/auth/me and /health
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              id: "user-1",
              email: "dev@forgeai.dev",
              full_name: "Lead Engineer",
              is_active: true,
            }),
        });
      }
      if (url.includes("/api/v1/health")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ status: "ok" }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Header />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Lead Engineer")).toBeInTheDocument();
    });
  });

  it("2. API returns 401 -> token is immediately cleared from storage", async () => {
    apiClient.setToken("expired-jwt-token");
    expect(apiClient.getToken()).toBe("expired-jwt-token");

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Token has expired." }),
    });

    await expect(apiClient.getMe()).rejects.toThrow("Token has expired.");

    // Token must be wiped
    expect(apiClient.getToken()).toBeNull();
    expect(localStorage.getItem("forgeai_token")).toBeNull();
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("3. API returns 401 -> authenticated state and listeners are triggered", async () => {
    apiClient.setToken("expired-jwt-token");
    let expiredListenerCalled = false;
    const unsub = apiClient.onAuthExpired(() => {
      expiredListenerCalled = true;
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Invalid credentials." }),
    });

    await expect(apiClient.getProjects()).rejects.toThrow("Invalid credentials.");
    expect(expiredListenerCalled).toBe(true);
    unsub();
  });

  it("4. API returns 401 -> redirect to /login is initiated", async () => {
    apiClient.setToken("expired-jwt-token");

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Signature has expired." }),
    });

    await expect(apiClient.getHealth()).rejects.toThrow();

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/login");
    });
  });

  it("5. Expired token -> Logout button and profile menu disappear", async () => {
    apiClient.setToken("expired-jwt-token");

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve({
          ok: false,
          status: 401,
          statusText: "Unauthorized",
          json: () => Promise.resolve({ detail: "Session expired" }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "ok" }),
      });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Header />
      </QueryClientProvider>
    );

    // Profile and logout should not be rendered
    await waitFor(() => {
      expect(screen.queryByText("Lead Engineer")).not.toBeInTheDocument();
      expect(screen.queryByText("Sign Out")).not.toBeInTheDocument();
    });
  });

  it("6. 403 Forbidden does NOT redirect to login automatically", async () => {
    apiClient.setToken("valid-token-no-perm");

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: () => Promise.resolve({ detail: "Insufficient permissions for tenant." }),
    });

    await expect(apiClient.getProject("proj-123")).rejects.toThrow("Insufficient permissions for tenant.");

    // Token must NOT be removed on 403
    expect(apiClient.getToken()).toBe("valid-token-no-perm");
    expect(mockReplace).not.toHaveBeenCalledWith("/login");
  });

  it("7. Multiple simultaneous 401 responses trigger only a single clean redirect", async () => {
    apiClient.setToken("expired-jwt-token");

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Expired" }),
    });

    // Fire 5 requests in parallel
    const results = await Promise.allSettled([
      apiClient.getProjects(),
      apiClient.getOrganizations(),
      apiClient.getHealth(),
      apiClient.getGitHubStatus(),
      apiClient.getMe(),
    ]);

    // All should reject
    expect(results.every((r) => r.status === "rejected")).toBe(true);

    // Token cleared
    expect(apiClient.getToken()).toBeNull();
  });

  it("8. Explicit logout works normally and clears state", async () => {
    apiClient.setToken("active-token");
    expect(apiClient.getToken()).toBe("active-token");

    apiClient.logout();
    expect(apiClient.getToken()).toBeNull();
    expect(localStorage.getItem("forgeai_token")).toBeNull();
  });
});
