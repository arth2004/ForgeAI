# Forge AI — Phase 7B GitHub PR Reviewer Runtime Specification

## Document Metadata
- **Status:** Verified Implementation
- **Release:** v0.7.0
- **Scope:** GitHub Webhooks, PR Ingestion, and Scoped Multi-Agent Reviewer Runtime (Phase 7B)
- **Baseline Release:** v0.6.0 ("Multi-Agent Software Engineering Platform")
- **Author:** Forge AI Engineering Team
- **Date:** August 2026

---

## 1. Overview & Scope

Phase 7B connects real-world GitHub Pull Request events to Forge AI's verified Multi-Agent `ReviewerAgent`. When a developer opens or updates a Pull Request on GitHub, Forge AI:
1. Validates the webhook payload using constant-time cryptographic HMAC-SHA256 verification.
2. Deduplicates repeated deliveries using `X-GitHub-Delivery` tracking.
3. Resolves the GitHub repository to an authorized Forge AI project and organization.
4. Creates an immutable `PullRequestSnapshot` bound to the exact base and head commit SHAs.
5. Extracts the scoped unified diff and maps modified lines to indexed AST code symbols.
6. Runs `ReviewerAgent` to audit the diff for security vulnerabilities (CWE/OWASP) and regressions.
7. Persists structured `AgentReview` and `ReviewFinding` records in PostgreSQL.
8. Exposes review findings and lifecycle status in Forge AI's web UI.

### Strict Scope Boundary
- **Read-Only GitHub Interaction**: Phase 7B does **NOT** publish review comments, does not request changes on GitHub, does not apply patches, and does not create/merge branches or PRs.
- **Preserved Safety**: All Phase 5 Human Approval Gates (`PLAN`, `DIFF`, `COMMIT`, `PUSH`, `PR_CREATE`) remain authoritative.

---

## 2. Architecture & Data Flow

```
                               GITHUB WEBHOOK
                                     │ (HMAC-SHA256 signed)
                                     ▼
                   ┌───────────────────────────────────┐
                   │    POST /api/v1/github/webhooks   │
                   │ (Signature & Delivery Validation) │
                   └─────────────────┬─────────────────┘
                                     │
                        [202 Accepted + Async Dispatch]
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │        PRIngestionService         │
                   │ (Tenant Binding, Immutable Snap)  │
                   └─────────────────┬─────────────────┘
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │        DiffContextService         │
                   │   (Scoped Diff + AST Symbols)     │
                   └─────────────────┬─────────────────┘
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │           ReviewerAgent           │
                   │    (Adversarial Security Audit)   │
                   └─────────────────┬─────────────────┘
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │        SHA Drift Protection       │
                   │ (Verify Head SHA is still latest) │
                   └─────────────────┬─────────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             │ (Head SHA Matches)                            │ (Head SHA Drifted)
             ▼                                               ▼
┌─────────────────────────┐                     ┌─────────────────────────┐
│ State: REVIEW_READY     │                     │ State: STALE            │
│ Findings Persisted      │                     │ Superseded by newer SHA │
└─────────────────────────┘                     └─────────────────────────┘
```

---

## 3. Database Schema (Migration `0010_github_pr_reviewer.py`)

### 1. `github_installations`
- `id`: UUID (PK)
- `organization_id`: UUID (FK to `organizations.id`)
- `installation_id`: BigInteger (Unique, Indexed)
- `account_name`: String(255)
- `account_type`: String(50)
- `permissions`: JSONB

### 2. `github_repository_bindings`
- `id`: UUID (PK)
- `installation_id`: UUID (FK to `github_installations.id`)
- `repository_id`: UUID (FK to `repositories.id`)
- `github_repo_id`: BigInteger (Indexed)
- `is_active`: Boolean
- `auto_review_enabled`: Boolean
- `auto_review_drafts`: Boolean
- `min_severity_to_comment`: String(16)
- *Constraint*: `UNIQUE(installation_id, repository_id)`

### 3. `pull_request_snapshots`
- `id`: UUID (PK)
- `repository_binding_id`: UUID (FK to `github_repository_bindings.id`)
- `pr_number`: Integer (Indexed)
- `title`: String(512)
- `body_summary`: Text
- `author_username`: String(255)
- `base_branch`: String(255)
- `base_sha`: String(40)
- `head_branch`: String(255)
- `head_sha`: String(40, Indexed)
- `is_draft`: Boolean
- `changed_files_count`: Integer
- *Constraint*: `UNIQUE(repository_binding_id, pr_number, head_sha)`

### 4. `pull_request_review_tasks`
- `id`: UUID (PK)
- `snapshot_id`: UUID (FK to `pull_request_snapshots.id`)
- `agent_task_id`: UUID (FK to `agent_tasks.id`, nullable)
- `agent_review_id`: UUID (FK to `agent_reviews.id`, nullable)
- `lifecycle_state`: Enum (`RECEIVED`, `VALIDATING`, `SNAPSHOTTING`, `QUEUED`, `ANALYZING`, `REVIEW_READY`, `SHA_VALIDATION`, `STALE`, `FAILED`, `REJECTED`)
- `active_agent`: String(32) (Default `REVIEWER`)
- `total_findings_count`: Integer
- `critical_count`: Integer
- `high_count`: Integer
- `started_at`: DateTime(timezone=True)
- `completed_at`: DateTime(timezone=True)
- `failure_reason`: Text

### 5. `github_webhook_deliveries`
- `id`: UUID (PK)
- `delivery_id`: String(64) (Unique, Indexed)
- `event_type`: String(64)
- `action`: String(64)
- `repository_id`: BigInteger
- `received_at`: DateTime(timezone=True)

---

## 4. REST API Reference

### Webhook Receiver
- `POST /api/v1/github/webhooks`
  - Headers: `X-Hub-Signature-256`, `X-GitHub-Delivery`, `X-GitHub-Event`
  - Response: `202 Accepted` with `delivery_id`, `task_id`, `snapshot_id`.

### Pull Request Queries
- `GET /api/v1/github/pulls/{snapshot_id}`
  - Returns `PRReviewTaskResponse` with PR metadata and finding summary metrics.
- `GET /api/v1/github/pulls/{snapshot_id}/findings`
  - Returns list of `PRReviewFindingResponse` with file locations, severity, descriptions, evidence, and remediation advice.
- `GET /api/v1/github/repositories/{repository_id}/pulls`
  - Lists recent PR review tasks for an indexed repository.

---

## 5. Security & Isolation Invariants

1. **HMAC-SHA256 Signature Verification**: All incoming webhooks must present a valid `X-Hub-Signature-256` matching `settings.GITHUB_WEBHOOK_SECRET`.
2. **Payload Sanitization**: Untrusted PR titles, descriptions, and comments are sanitized to strip script tags and JavaScript execution vectors before database persistence.
3. **Prompt Demarcation**: All PR diffs are wrapped inside `<PULL_REQUEST_DIFF_UNTRUSTED_CONTENT>` tags in model prompts to prevent prompt injection.
4. **Credential Isolation**: GitHub App installation tokens are generated on demand with a 1-hour TTL and never exposed in logs, SSE streams, or database tables.
5. **Zero Autonomous Mutation**: Review findings are strictly advisory; no mutations to GitHub repositories occur without human initiation and approval.
