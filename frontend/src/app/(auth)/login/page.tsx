"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Terminal, Lock, Mail, ArrowRight, ShieldCheck } from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("developer@forgeai.dev");
  const [password, setPassword] = useState("DeveloperPassword123!");
  const [fullName, setFullName] = useState("Forge Developer");
  const [orgName, setOrgName] = useState("Acme Labs");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        await apiClient.register({
          email,
          password,
          full_name: fullName,
          organization_name: orgName,
        });
      } else {
        await apiClient.login({ email, password });
      }
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Authentication failed. Please check credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background selection:bg-sky-500/20">
      <div className="w-full max-w-md space-y-6">
        {/* Brand */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center mx-auto shadow-xl shadow-sky-500/20">
            <Terminal className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            {isRegister ? "Create Developer Account" : "Sign In to Forge AI"}
          </h1>
          <p className="text-xs text-muted-foreground">
            Phase 1 Foundation • Multi-tenant Workspace Authentication
          </p>
        </div>

        {/* Auth Box */}
        <div className="p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl shadow-xl space-y-5">
          {error && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            {isRegister && (
              <>
                <div>
                  <label className="block text-muted-foreground font-medium mb-1">Full Name</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                  />
                </div>
                <div>
                  <label className="block text-muted-foreground font-medium mb-1">
                    Organization Name
                  </label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-muted-foreground font-medium mb-1">Email Address</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                />
              </div>
            </div>

            <div>
              <label className="block text-muted-foreground font-medium mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-semibold text-xs shadow-md shadow-sky-500/20 transition-all disabled:opacity-50"
            >
              <span>{loading ? "Authenticating..." : isRegister ? "Sign Up" : "Sign In"}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>

          {/* Toggle between Login & Register */}
          <div className="text-center pt-2 border-t border-border/40 text-xs">
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister);
                setError(null);
              }}
              className="text-muted-foreground hover:text-sky-400 transition-colors"
            >
              {isRegister
                ? "Already have an account? Sign in"
                : "Need a new test account? Register"}
            </button>
          </div>
        </div>

        {/* Phase Note */}
        <div className="flex items-center justify-center gap-2 text-[11px] text-muted-foreground text-center">
          <ShieldCheck className="w-3.5 h-3.5 text-sky-400" />
          <span>GitHub OAuth login arrives in Phase 2</span>
        </div>
      </div>
    </div>
  );
}
