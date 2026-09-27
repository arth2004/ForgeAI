"""Scoped Diff Parsing and AST Context Retrieval Service for GitHub PR Reviewer."""

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.codebase import CodeChunk, CodeDependency, RepositoryFile
from app.models.github import PullRequestSnapshot
from app.services.github.client import github_client
from app.services.github.sanitizer import wrap_untrusted_content

logger = logging.getLogger(__name__)


class DiffContextService:
    """Handles PR unified diff extraction, AST symbol identification, and targeted context expansion."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def fetch_pr_diff(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> str:
        """Fetches the unified diff of a PR with size limit enforcement."""
        diff_text = await github_client.get_pull_request_diff(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            pull_number=pr_number,
        )

        diff_bytes = len(diff_text.encode("utf-8"))
        if diff_bytes > settings.MAX_PR_DIFF_BYTES:
            logger.warning(
                "PR diff exceeds maximum allowable size (%d > %d bytes). Truncating diff.",
                diff_bytes,
                settings.MAX_PR_DIFF_BYTES,
            )
            # Truncate at character boundary with note
            diff_text = diff_text[: settings.MAX_PR_DIFF_BYTES] + "\n\n... [DIFF TRUNCATED DUE TO SIZE LIMIT] ...\n"

        return diff_text

    def parse_changed_files_from_diff(self, diff_text: str) -> list[dict[str, Any]]:
        """Parses unified diff into structured per-file modifications and hunk line ranges."""
        changed_files: list[dict[str, Any]] = []
        if not diff_text:
            return changed_files

        file_diffs = re.split(r"^diff --git ", diff_text, flags=re.MULTILINE)
        for chunk in file_diffs:
            if not chunk.strip():
                continue

            lines = chunk.split("\n")
            first_line = lines[0]
            # Match a/path b/path
            paths = first_line.split(" ")
            if len(paths) < 2:
                continue

            orig_path = paths[0].removeprefix("a/")
            new_path = paths[1].removeprefix("b/")
            target_path = new_path if new_path != "/dev/null" else orig_path

            operation = "MODIFY"
            if "--- /dev/null" in chunk or "new file mode" in chunk or orig_path == "/dev/null":
                operation = "CREATE"
            elif "+++ /dev/null" in chunk or "deleted file mode" in chunk or new_path == "/dev/null":
                operation = "DELETE"


            # Extract hunk line ranges: @@ -start,len +start,len @@
            hunks: list[dict[str, int]] = []
            for line in lines:
                if line.startswith("@@"):
                    match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
                    if match:
                        new_start = int(match.group(2))
                        new_len = int(match.group(3)) if match.group(3) else 1
                        hunks.append({
                            "start_line": new_start,
                            "end_line": new_start + new_len - 1,
                        })

            changed_files.append({
                "file_path": target_path,
                "operation": operation,
                "hunks": hunks,
            })

            if len(changed_files) >= settings.MAX_PR_CHANGED_FILES:
                logger.warning("Reached MAX_PR_CHANGED_FILES limit (%d). Capping parsed files.", settings.MAX_PR_CHANGED_FILES)
                break

        return changed_files

    async def extract_changed_symbols(
        self,
        repository_id: uuid.UUID,
        changed_files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Finds indexed AST code symbols corresponding to modified line ranges in changed files."""
        symbols: list[dict[str, Any]] = []
        if not changed_files:
            return symbols

        file_paths = [f["file_path"] for f in changed_files if f["operation"] != "DELETE"]
        if not file_paths:
            return symbols

        q = (
            select(CodeChunk, RepositoryFile.file_path)
            .join(RepositoryFile, CodeChunk.file_id == RepositoryFile.id)
            .where(
                RepositoryFile.repository_id == repository_id,
                RepositoryFile.file_path.in_(file_paths),
            )
        )
        res = await self.db.execute(q)
        rows = res.all()

        for chunk, path in rows:
            # Check if chunk lines overlap with any hunk in the changed file
            file_info = next((f for f in changed_files if f["file_path"] == path), None)
            if not file_info:
                continue

            hunks = file_info.get("hunks", [])
            overlaps = False
            if not hunks:
                overlaps = True
            else:
                for h in hunks:
                    if not (chunk.end_line < h["start_line"] or chunk.start_line > h["end_line"]):
                        overlaps = True
                        break

            if overlaps:
                symbols.append({
                    "chunk_id": str(chunk.id),
                    "symbol_name": chunk.symbol_name or "anonymous_block",
                    "symbol_type": str(chunk.chunk_type),
                    "file_path": path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                })

        return symbols

    async def retrieve_surrounding_context(
        self,
        repository_id: uuid.UUID,
        changed_symbols: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Retrieves related callers, callees, and dependencies for the changed symbols."""
        surrounding_context: list[dict[str, Any]] = []
        symbol_names = [s["symbol_name"] for s in changed_symbols if s.get("symbol_name") and s["symbol_name"] != "anonymous_block"]
        if not symbol_names:
            return surrounding_context

        # Look up dependency edges
        dep_q = (
            select(CodeDependency)
            .where(
                CodeDependency.repository_id == repository_id,
                CodeDependency.source_symbol.in_(symbol_names),
            )
            .limit(15)
        )
        res = await self.db.execute(dep_q)
        deps = res.scalars().all()

        for dep in deps:
            surrounding_context.append({
                "type": str(dep.dependency_type),
                "symbol_name": dep.target_symbol or dep.imported_path,
                "symbol_type": "DEPENDENCY",
                "content": f"Imported from {dep.imported_path}",
            })

        return surrounding_context

    def format_review_prompt(
        self,
        snapshot: PullRequestSnapshot,

        diff_text: str,
        changed_symbols: list[dict[str, Any]],
        surrounding_context: list[dict[str, Any]],
    ) -> str:
        """Formats the structured review prompt with strict untrusted data boundaries."""
        prompt_parts: list[str] = [
            f"Reviewing GitHub Pull Request #{snapshot.pr_number}: {snapshot.title}",
            f"Author: {snapshot.author_username}",
            f"Base: {snapshot.base_branch} ({snapshot.base_sha[:8]}) -> Head: {snapshot.head_branch} ({snapshot.head_sha[:8]})",
            "",
            wrap_untrusted_content("PR_DESCRIPTION", snapshot.body_summary),
            "",
            wrap_untrusted_content("PULL_REQUEST_DIFF", diff_text),
        ]

        if changed_symbols:
            symbols_summary = "\n".join(
                f"- {s['symbol_type']} `{s['symbol_name']}` in {s['file_path']}:L{s['start_line']}-{s['end_line']}"
                for s in changed_symbols[:20]
            )
            prompt_parts.extend([
                "",
                "Changed AST Symbols:",
                symbols_summary,
            ])

        if surrounding_context:
            context_summary = "\n".join(
                f"[{ctx['type']}] {ctx['symbol_type']} `{ctx['symbol_name']}`:\n{ctx['content']}"
                for ctx in surrounding_context[:5]
            )
            prompt_parts.extend([
                "",
                "Surrounding Context & AST Dependencies:",
                context_summary,
            ])

        prompt_parts.extend([
            "",
            "Analyze the diff for security vulnerabilities (CWE/OWASP), regression risks, concurrency issues, and broken contracts.",
            "Return structured JSON conforming to the Reviewer Agent output format.",
        ])

        return "\n".join(prompt_parts)
