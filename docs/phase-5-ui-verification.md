# Forge AI v0.5.0 — Phase 5 UI Verification, Dashboard Update & Auth Expiry Report

**Date:** 2026-08-23  
**Target Version:** `v0.5.0`  
**Status:** COMPLETE & VERIFIED

---

## 1. Overview

This document records the UI verification, dashboard overhaul, and authentication expiry handling audit for **Forge AI v0.5.0**.

---

## 2. Phase 5 Component Verification

### Phase 5B: Implementation Plan UI (`AgentPlanView.tsx`)
- **Visual Fields**:
  - Summary, Problem Statement, Approach.
  - Affected Files with change operations (`CREATE`, `MODIFY`, `DELETE`), reasoning, and touched symbols.
  - New Files, Deleted Files, Test Strategy, Risks, and grounded Source Citations.
- **Gate 1 Approval Actions**:
  - `[Approve Plan]` triggers `POST /api/v1/agent/approvals/{approval_id}/approve` and provisions ephemeral workspace via `POST /api/v1/agent/workspaces`.
  - `[Reject Plan]` triggers `POST /api/v1/agent/approvals/{approval_id}/reject`.
- **Security**: Server-side authorization remains strictly authoritative.

### Phase 5C: Proposed Patch & Unified Diff UI (`AgentDiffView.tsx`)
- **Visual Fields**:
  - Unified color-coded diff viewer with addition/deletion line counters (`+`, `-`).
  - Affected file list, patch summary, and status badges (`PROPOSED`, `AWAITING_APPROVAL`, `APPROVED`, `APPLIED`, `CONFLICT`, `REJECTED`).
- **Gate 2 Diff Actions**:
  - `[Approve Diff]` records human approval for the specific diff.
  - `[Reject Diff]` rejects the proposal and updates status.
  - `[Apply Patch]` triggers atomic transactional file modification.

### Phase 5C: Sandboxed Test Execution UI (`AgentTestPanel.tsx`)
- **Visual Fields**:
  - Test runner name (`pytest`, `ruff`, `npm_test`) and CLI arguments.
  - Execution status (`QUEUED`, `RUNNING`, `PASSED`, `FAILED`, `TIMEOUT`, `SANDBOX_UNAVAILABLE`).
  - Exit code badge (color-coded for 0 vs non-zero).
  - Execution duration in milliseconds.
  - Terminal output viewer for sanitized `stdout` and `stderr`.

### Phase 5D: Git & GitHub PR Integration UI (`AgentGitPanel.tsx`)
- **Visual Fields**:
  - Active feature branch badge (`forge/{session_id_prefix}`).
  - Commit status, commit SHA link, and commit message review.
  - Remote feature branch push status.
  - GitHub Pull Request status, PR number badge, and direct URL link.
- **Gates 3, 4, 5 Actions**:
  - Gate 3 (COMMIT): `[Approve Commit]` $\rightarrow$ `[Commit Changes]`.
  - Gate 4 (PUSH): `[Approve Push]` $\rightarrow$ `[Push Branch]`.
  - Gate 5 (PR_CREATE): `[Approve PR Creation]` $\rightarrow$ `[Create Pull Request]`.

---

## 3. Server-Sent Events (SSE) Stream Integration

The SSE stream parser and `useAgentChat` hook were upgraded to support all Phase 4 and Phase 5 event types:
1. `session.created`
2. `agent.started`
3. `agent.tool_call`
4. `agent.tool_result`
5. `agent.completed`
6. `agent.error`
7. `agent.plan.created`
8. `agent.approval.required`
9. `agent.approval.resolved`
10. `agent.workspace.created`
11. `agent.patch.proposed`
12. `agent.patch.applied`
13. `agent.test.started`
14. `agent.test.completed`
15. `agent.commit.created`
16. `agent.pr.created`

---

## 4. Phase 5 Dashboard Update (`page.tsx`)

The dashboard was overhauled to reflect Forge AI v0.5.0:
- **Banner**: "FORGE AI — Repository Intelligence $\rightarrow$ AI Software Engineering" with `Forge AI v0.5.0` release badges.
- **Visual Lifecycle**: Interactive 7-step visualization:
  1. Understand (AST + Hybrid Search)
  2. Plan (Gate 1: PLAN)
  3. Workspace (Isolated Git Tree)
  4. Review (Gate 2: DIFF)
  5. Test (Sandboxed Container)
  6. Git Ops (Gate 3: COMMIT & Gate 4: PUSH)
  7. Pull Request (Gate 5: PR_CREATE)
- **Security & Guardrail Card**: Explicitly displays that autonomous remote mutations are prevented and all 5 human gates are enforced.
- **Project & Infrastructure Overview**: Live project list with connected repositories, FastAPI Gateway, PostgreSQL pgvector, Redis broker, and ARQ worker verification.

---

## 5. Critical Authentication Expiry Bug Fix

### Root Cause
Previously, the frontend checked `!!token` against localStorage/sessionStorage string presence without verifying token validity. When API requests received HTTP `401 Unauthorized`, the client threw an unhandled error but did not purge stored tokens or reset the authenticated user state. As a result, the user profile dropdown and Logout button remained rendered, and no automatic redirection to `/login` took place.

### Solution Implemented
1. **Centralized 401 Interceptor**:
   In `ApiClient.request()`, any response with status `401` invokes `handleAuthExpired()`.
2. **Immediate Storage & State Cleanup**:
   Purges `forgeai_token`, `forgeai_auth`, `auth_token`, and `access_token` from both `localStorage` and `sessionStorage`.
3. **Event Dispatch & Cache Purge**:
   Dispatches `"forgeai:auth-expired"` to notify React components to clear query caches (`queryClient.clear()`) and reset navigation state.
4. **Clean Redirection**:
   Safely redirects browser location to `/login` while preventing recursive redirect loops and avoiding redirection if the user is already on `/login` or `/register`.
5. **403 Distinction**:
   HTTP `403 Forbidden` responses remain treated as permission/authorization errors without clearing tokens or triggering redirection.

---

## 6. Verification & Test Baseline

- **Backend Test Suite**: `243 / 243 passed`
- **Frontend Test Suite**: `33 / 33 passed`
- **Ruff Linter**: Clean (0 errors)
- **Mypy Static Typing**: Clean (0 errors across 98 source files)
- **Next.js Production Build**: Succeeded (`8 / 8 static pages generated`)
