"use client";

import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings,
  Shield,
  Key,
  Database,
  Building,
  Save,
  CheckCircle2,
  Lock,
  Github,
  ShieldCheck,
  AlertCircle,
  Unlink,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [orgName, setOrgName] = useState("");
  const [isSaved, setIsSaved] = useState(false);
  const [urlMessage, setUrlMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Check URL query parameters for OAuth callback redirects
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("github") === "connected") {
        setUrlMessage({ type: "success", text: "GitHub account and repositories successfully connected!" });
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (params.get("error")) {
        setUrlMessage({ type: "error", text: `GitHub connection failed: ${params.get("error")}` });
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }
  }, []);

  // 1. Organizations Query
  const { data: orgs, isLoading: orgsLoading } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiClient.getOrganizations(),
    retry: 1,
  });

  // 2. GitHub Status Query
  const { data: githubStatus, isLoading: githubLoading } = useQuery({
    queryKey: ["github-status"],
    queryFn: () => apiClient.getGitHubStatus(),
    retry: 1,
  });

  // 3. Connect GitHub Mutation
  const connectGitHubMutation = useMutation({
    mutationFn: () => apiClient.getGitHubAuthorizeUrl(),
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (err: any) => {
      setUrlMessage({ type: "error", text: err.message || "Failed to initialize GitHub authorization." });
    },
  });

  // 4. Disconnect GitHub Mutation
  const disconnectGitHubMutation = useMutation({
    mutationFn: () => apiClient.disconnectGitHub(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["github-status"] });
      setUrlMessage({ type: "success", text: "GitHub account disconnected." });
    },
    onError: (err: any) => {
      setUrlMessage({ type: "error", text: err.message || "Failed to disconnect GitHub." });
    },
  });

  const createOrgMutation = useMutation({
    mutationFn: (name: string) => apiClient.createOrganization({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setOrgName("");
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 3000);
    },
  });

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Platform & Integrations Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage organizations, GitHub repository access permissions, and underlying security configuration.
        </p>
      </div>

      {urlMessage && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between text-xs font-medium ${
            urlMessage.type === "success"
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
              : "bg-destructive/10 border-destructive/20 text-destructive"
          }`}
        >
          <div className="flex items-center gap-2">
            {urlMessage.type === "success" ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <AlertCircle className="w-4 h-4" />
            )}
            <span>{urlMessage.text}</span>
          </div>
          <button
            onClick={() => setUrlMessage(null)}
            className="text-muted-foreground hover:text-foreground text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="space-y-6">
        {/* GitHub Integration Card (Phase 2) */}
        <div className="p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Github className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">
                  GitHub Integration
                </h2>
                <p className="text-xs text-muted-foreground">
                  Connect your GitHub account or organization using fine-grained, read-only permissions.
                </p>
              </div>
            </div>

            {githubStatus?.is_connected ? (
              <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium border border-emerald-500/20 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" />
                Connected
              </span>
            ) : (
              <span className="text-xs px-2.5 py-1 rounded-full bg-muted text-muted-foreground font-medium border">
                Not Connected
              </span>
            )}
          </div>

          {githubLoading ? (
            <div className="h-20 rounded-xl bg-secondary/40 animate-pulse" />
          ) : githubStatus?.is_connected ? (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl bg-secondary/30 border border-border/40 gap-4">
                <div className="flex items-center gap-3">
                  {githubStatus.avatar_url ? (
                    <img
                      src={githubStatus.avatar_url}
                      alt={githubStatus.github_username || "GitHub Avatar"}
                      className="w-11 h-11 rounded-full border border-border/60"
                    />
                  ) : (
                    <div className="w-11 h-11 rounded-full bg-primary/10 flex items-center justify-center font-bold text-primary">
                      {githubStatus.github_username?.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-foreground">
                        @{githubStatus.github_username}
                      </span>
                      {githubStatus.github_installation_id && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                          App Inst #{githubStatus.github_installation_id}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                      Permissions: <code className="text-[11px] bg-muted px-1 py-0.5 rounded font-mono">Contents: Read</code>, <code className="text-[11px] bg-muted px-1 py-0.5 rounded font-mono">Metadata: Read</code> (0 write permissions)
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <button
                    onClick={() => disconnectGitHubMutation.mutate()}
                    disabled={disconnectGitHubMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-destructive/10 text-destructive hover:bg-destructive/20 border border-destructive/20 transition-colors"
                  >
                    {disconnectGitHubMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Unlink className="w-3.5 h-3.5" />
                    )}
                    <span>Disconnect</span>
                  </button>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-accent/20 border border-border/30 text-xs text-muted-foreground flex items-start gap-2.5">
                <ShieldCheck className="w-4 h-4 text-purple-400 flex-shrink-0 mt-0.5" />
                <span>
                  Forge AI uses short-lived, 1-hour Installation Access Tokens generated on demand using our App's private key. Tokens are never persisted in databases or exposed to browsers.
                </span>
              </div>
            </div>
          ) : (
            <div className="p-5 rounded-xl bg-secondary/20 border border-border/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="space-y-1 max-w-xl">
                <h3 className="text-sm font-semibold text-foreground">
                  Connect GitHub App
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Authorize Forge AI to read repository code structures, list branches, and prepare codebases for semantic ingestion with strict least-privilege permissions.
                </p>
              </div>
              <button
                onClick={() => connectGitHubMutation.mutate()}
                disabled={connectGitHubMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity shadow-sm whitespace-nowrap"
              >
                {connectGitHubMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Github className="w-4 h-4" />
                )}
                <span>Connect GitHub</span>
              </button>
            </div>
          )}
        </div>

        {/* Organizations Section */}
        <div className="p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
              <Building className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">
                Organizations & Tenants
              </h2>
              <p className="text-xs text-muted-foreground">
                Configure your multi-tenant organizations and workspaces.
              </p>
            </div>
          </div>

          {/* Org List */}
          <div className="space-y-3">
            {orgsLoading ? (
              <div className="h-16 rounded-xl bg-secondary/40 animate-pulse" />
            ) : orgs && orgs.length > 0 ? (
              orgs.map((org) => (
                <div
                  key={org.id}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-secondary/30 border border-border/40 text-xs"
                >
                  <div>
                    <span className="font-semibold text-foreground">{org.name}</span>
                    <span className="ml-2 font-mono text-[11px] text-muted-foreground">
                      slug: {org.slug}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
                    ID: {org.id.slice(0, 8)}...
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground">No organizations registered yet.</p>
            )}
          </div>

          {/* Create Org Form */}
          <div className="flex items-center gap-3 pt-2">
            <input
              type="text"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="New organization name..."
              className="flex-1 px-3 py-2 text-xs rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
            />
            <button
              onClick={() => orgName.trim() && createOrgMutation.mutate(orgName.trim())}
              disabled={!orgName.trim() || createOrgMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-sky-500 hover:bg-sky-400 text-white disabled:opacity-50 transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{createOrgMutation.isPending ? "Creating..." : "Add Organization"}</span>
            </button>
          </div>

          {isSaved && (
            <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 rounded-lg">
              <CheckCircle2 className="w-4 h-4" />
              <span>Organization successfully created!</span>
            </div>
          )}
        </div>

        {/* Security & Cryptography Specification */}
        <div className="p-6 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-xl space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">
                Security & Encryption Profile
              </h2>
              <p className="text-xs text-muted-foreground">
                Symmetric AES-256-GCM authenticated encryption and token protections.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 text-xs">
            <div className="p-4 rounded-xl bg-secondary/30 border border-border/40 space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-foreground">
                <Lock className="w-3.5 h-3.5 text-sky-400" />
                <span>Credential Encryption</span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed">
                Tokens at rest are encrypted via AES-256-GCM using hardware-accelerated OpenSSL primitives.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-secondary/30 border border-border/40 space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-foreground">
                <Key className="w-3.5 h-3.5 text-sky-400" />
                <span>Session Signatures</span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed">
                HMAC-SHA256 JWT tokens configured with centralized expiration and revocation validation.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
