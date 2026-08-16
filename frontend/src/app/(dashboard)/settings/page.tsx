"use client";

import React, { useState } from "react";
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
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [orgName, setOrgName] = useState("");
  const [isSaved, setIsSaved] = useState(false);

  const { data: orgs, isLoading } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiClient.getOrganizations(),
    retry: 1,
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
          Platform & Tenant Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage organizations, security parameters, and underlying infrastructure configuration.
        </p>
      </div>

      <div className="space-y-6">
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
            {isLoading ? (
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
