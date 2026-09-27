import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { PullRequestReviewCard } from "@/components/agent/PullRequestReviewCard";
import { PRReviewTask } from "@/types/agent";

describe("Phase 7B / 7C GitHub PR Review UI Component", () => {
  const baseTask: PRReviewTask = {
    id: "task-pr-1",
    snapshot_id: "snap-pr-1",
    snapshot: {
      id: "snap-pr-1",
      repository_binding_id: "bind-1",
      pr_number: 42,
      title: "Fix Token Bucket Float Precision",
      author_username: "octocat",
      base_branch: "main",
      base_sha: "1111111111111111111111111111111111111111",
      head_branch: "fix-tokens",
      head_sha: "2222222222222222222222222222222222222222",
      is_draft: false,
      changed_files_count: 2,
      created_at: new Date().toISOString(),
    },
    lifecycle_state: "REVIEW_READY",
    active_agent: "REVIEWER",
    total_findings_count: 1,
    critical_count: 1,
    high_count: 0,
    findings: [
      {
        id: "find-1",
        severity: "CRITICAL",
        category: "SECURITY",
        file_path: "app/core/rate_limiter.py",
        start_line: 42,
        end_line: 45,
        description: "Float rounding causes negative token balances under concurrency",
        evidence: "tokens = tokens - float(requested)",
        recommendation: "Use Decimal arithmetic or integer micro-tokens",
      },
    ],
  };

  it("renders PR title, author, and branch metadata cleanly", () => {
    render(<PullRequestReviewCard reviewTask={baseTask} />);

    expect(screen.getByText("PR #42")).toBeDefined();
    expect(screen.getByText("Fix Token Bucket Float Precision")).toBeDefined();
    expect(screen.getByText("octocat")).toBeDefined();
    expect(screen.getByText("main")).toBeDefined();
    expect(screen.getByText("fix-tokens")).toBeDefined();
  });

  it("renders REVIEW READY badge and structured findings in read-only mode", () => {
    render(<PullRequestReviewCard reviewTask={baseTask} />);

    expect(screen.getByTestId("pr-review-ready-badge")).toBeDefined();
    expect(screen.getByText("Float rounding causes negative token balances under concurrency")).toBeDefined();
    expect(screen.getAllByText(/Critical/i).length).toBeGreaterThan(0);
    expect(screen.getByText("app/core/rate_limiter.py")).toBeDefined();
  });

  it("renders clean REVIEW READY state when model returns zero findings", () => {
    const cleanTask: PRReviewTask = {
      ...baseTask,
      lifecycle_state: "REVIEW_READY",
      total_findings_count: 0,
      critical_count: 0,
      high_count: 0,
      findings: [],
    };

    render(<PullRequestReviewCard reviewTask={cleanTask} />);

    expect(screen.getByTestId("pr-review-ready-badge")).toBeDefined();
    expect(screen.getByText("No security or regression findings detected on this Pull Request snapshot.")).toBeDefined();
  });

  it("renders STALE warning banner when newer commit is pushed on GitHub", () => {
    const staleTask: PRReviewTask = {
      ...baseTask,
      lifecycle_state: "STALE",
    };

    render(<PullRequestReviewCard reviewTask={staleTask} />);

    expect(screen.getByTestId("pr-review-stale-badge")).toBeDefined();
    expect(screen.getByTestId("pr-review-stale-warning")).toBeDefined();
    expect(screen.getByText(/A newer commit was pushed to this pull request on GitHub/)).toBeDefined();
  });

  it("renders ANALYZING progress indicator when review is in progress", () => {
    const analyzingTask: PRReviewTask = {
      ...baseTask,
      lifecycle_state: "ANALYZING",
      findings: [],
    };

    render(<PullRequestReviewCard reviewTask={analyzingTask} />);

    expect(screen.getByTestId("pr-review-analyzing-badge")).toBeDefined();
    expect(screen.getByText("Review analysis in progress...")).toBeDefined();
  });

  it("renders FAILED badge and Reviewer unavailable banner with reason when review fails", () => {
    const failedTask: PRReviewTask = {
      ...baseTask,
      lifecycle_state: "FAILED",
      failure_reason: "Provider rate limit exceeded (HTTP 429)",
      findings: [],
    };

    render(<PullRequestReviewCard reviewTask={failedTask} />);

    expect(screen.getByTestId("pr-review-failed-badge")).toBeDefined();
    expect(screen.getByTestId("pr-review-failed-banner")).toBeDefined();
    expect(screen.getByText("Reviewer unavailable")).toBeDefined();
    expect(screen.getByText("The AI model could not complete this review.")).toBeDefined();
    expect(screen.getByText(/Provider rate limit exceeded \(HTTP 429\)/)).toBeDefined();
    // Must NOT show clean approval message
    expect(screen.queryByText("No security or regression findings detected on this Pull Request snapshot.")).toBeNull();
    expect(screen.queryByTestId("pr-review-ready-badge")).toBeNull();
  });
});
