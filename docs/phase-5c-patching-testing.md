# Forge AI — Phase 5C Architecture & Reference
## Safe Patch Synthesis & Sandboxed Test Execution

### 1. Overview & Security Boundary

Phase 5C implements structured patch proposal, server-side unified diff generation, human DIFF approval gating (Gate 2), atomic patch application with automatic rollback, and isolated container test execution.

```
Approved Plan (Gate 1)
      ↓
AgentWorkspace (Base Commit Recorded)
      ↓
propose_patch (Structured Tool/API)
      ↓
Server Validation (Path traversal, Bounds, Plan Grounding, Hash Verification)
      ↓
Server-Generated Unified Diff
      ↓
┌───────────────────────────────────────┐
│     HUMAN DIFF APPROVAL (Gate 2)      │
│ POST /api/v1/agent/patches/{id}/apply │
└──────────────────┬────────────────────┘
                   ↓
         apply_patch (Atomic)
         (Rollback on any failure)
                   ↓
         run_tests (Sandboxed)
  (--network=none, 2 vCPU, 2048 MB, 120s)
```

### 2. Strict Safety Constraints

1. **No Autonomous Patching:** `apply_patch` cannot be triggered by LLM tool calls. Attempting to invoke `apply_patch` via tool returns `APPROVAL_REQUIRED` until explicit human approval is recorded.
2. **Hash Drift Protection:** Every modified or deleted file is compared against its `old_content_hash`. If workspace state has drifted, a `PATCH_CONFLICT` error is raised.
3. **Server-Generated Diffs:** The model never supplies the diff preview; the server computes standard unified diffs via Python `difflib`.
4. **All-or-Nothing Rollback:** If any file write or post-application hash verification fails, the engine immediately restores all files to their pre-application state.
5. **No Shell Operators:** Declarative runners (`pytest`, `ruff`, `npm_test`, `cargo_test`) reject shell chaining operators (`&&`, `;`, `|`, `` ` ``, `$()`).
6. **Secret Isolation:** Environment secrets (API keys, database credentials, JWT secrets) are excluded from sandboxes and redacted from output logs.
7. **Resource & Output Bounds:** 2 vCPU, 2048 MB memory, `--network=none`, 120s timeout, max 100 KB / 500 lines log truncation.
8. **Sandbox Fallback:** If Docker is unavailable, tests report `SANDBOX_UNAVAILABLE`; execution never falls back to host execution.

### 3. API Reference

- `POST /api/v1/agent/patches/propose`: Proposes a structured patch proposal and generates pending Gate 2 approval.
- `GET /api/v1/agent/patches/{patch_id}`: Retrieves patch status and metadata.
- `GET /api/v1/agent/patches/{patch_id}/diff`: Retrieves server-generated unified diff preview.
- `POST /api/v1/agent/patches/{patch_id}/approve`: Explicit human approval of patch diff.
- `POST /api/v1/agent/patches/{patch_id}/reject`: Explicit human rejection of patch.
- `POST /api/v1/agent/patches/{patch_id}/apply`: Authoritatively applies approved patch to workspace.
- `POST /api/v1/agent/workspaces/{workspace_id}/tests`: Runs declarative test runner in sandbox.
- `GET /api/v1/agent/tests/{test_id}`: Retrieves sandboxed test execution report.
