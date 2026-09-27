"""Reviewer Agent Implementation for Phase 6 Multi-Agent Architecture."""

import json
import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import BaseChatModelProvider
from app.agent.multi_agent.base import BaseEngineeringAgent
from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.types import (
    AgentRoleEnum,
    ReviewCategory,
    ReviewFindingSchema,
    ReviewFindingSeverity,
    TaskLifecycleState,
)
from app.models.agent import AgentReview, ReviewFinding

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM_PROMPT = """You are the Forge AI Reviewer Agent.
Your responsibility is rigorous, adversarial static code review and security auditing of proposed patch diffs.

REVIEW CRITERIA:
1. Security: Check for SQL injection, command injection, path traversal, credential exposure, unsafe subprocess calls, insecure deserialization, and authentication bypasses.
2. Correctness & Regressions: Ensure edge cases are handled and existing contracts are preserved.
3. Test Coverage: Confirm modified symbols have corresponding test coverage.

OUTPUT FORMAT:
Return a JSON object with:
- "status": "APPROVED" or "CHANGES_REQUESTED"
- "summary": High-level evaluation summary
- "findings": List of findings (each with "severity": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW"|"INFO", "category", "file_path", "description", "recommendation")
"""


class ReviewerAgent(BaseEngineeringAgent):
    """Specialized agent dedicated to adversarial static code review and security auditing."""

    def __init__(self, model_provider: BaseChatModelProvider) -> None:
        super().__init__(
            model_provider=model_provider,
            role=AgentRoleEnum.REVIEWER,
            allowed_tools={"search_repository", "search_symbol", "get_file"},
        )

    async def execute(
        self,
        state: MultiAgentState,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Performs static code review and static analysis on active patch."""
        logger.info(
            "ReviewerAgent evaluating patch=%s for task=%s",
            state.get("active_patch_id"),
            state["task_id"],
        )

        active_patch = state.get("active_patch") or {}
        diff_content = active_patch.get("diff_content", "")

        # 1. Evaluate diff via adversarial LLM prompt
        messages = [
            SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Objective: {state['prompt']}\n"
                    f"Diff:\n{diff_content or 'No diff content available.'}\n"
                    f"Review the patch diff and provide structured JSON findings."
                )
            ),
        ]

        response = await self.model_provider.ainvoke(messages, tools=None)
        content_text = str(response.content)

        clean_json = content_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.removeprefix("```json").removesuffix("```").strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json.removeprefix("```").removesuffix("```").strip()

        try:
            parsed = json.loads(clean_json)
        except Exception as json_err:
            logger.error("ReviewerAgent received unparseable JSON response from model: %s", json_err)
            raise ValueError(f"Reviewer model response is not valid JSON: {json_err}") from json_err

        if not isinstance(parsed, dict):
            raise ValueError(f"Reviewer model response must be a JSON dictionary, got {type(parsed)}")

        raw_status = str(parsed.get("status", "")).upper()
        if raw_status not in {"APPROVED", "CHANGES_REQUESTED"}:
            raise ValueError(f"Invalid review status '{raw_status}' from model. Expected APPROVED or CHANGES_REQUESTED.")

        summary = str(parsed.get("summary", "Review completed."))
        raw_findings = parsed.get("findings", [])
        if not isinstance(raw_findings, list):
            raise ValueError(f"Reviewer findings must be a list, got {type(raw_findings)}")

        findings: list[dict[str, Any]] = []
        for f in raw_findings:
            if not isinstance(f, dict):
                raise ValueError(f"Review finding item must be a dictionary, got {type(f)}")

            raw_sev = str(f.get("severity", "INFO")).strip().upper()
            sev_val = ReviewFindingSeverity.INFO
            for s in ReviewFindingSeverity:
                if s.value in raw_sev:
                    sev_val = s
                    break

            raw_cat = str(f.get("category", "CORRECTNESS")).strip().upper()
            cat_val = ReviewCategory.CORRECTNESS
            if any(k in raw_cat for k in ("SEC", "INJECT", "AUTH", "VULN", "EXPOS", "CRED", "LEAK")):
                cat_val = ReviewCategory.SECURITY
            elif "REGRESS" in raw_cat:
                cat_val = ReviewCategory.REGRESSION
            elif any(k in raw_cat for k in ("CORRECT", "BUG", "ERROR", "VALID", "CONTRACT", "API", "SCHEMA")):
                cat_val = ReviewCategory.CORRECTNESS
            elif any(k in raw_cat for k in ("ARCH", "DESIGN", "STRUCT")):
                cat_val = ReviewCategory.ARCHITECTURE
            elif any(k in raw_cat for k in ("TEST", "COVER")):
                cat_val = ReviewCategory.TEST_COVERAGE
            elif any(k in raw_cat for k in ("STYLE", "LINT", "FORMAT", "NAMING")):
                cat_val = ReviewCategory.STYLE

            finding_obj = ReviewFindingSchema(
                severity=sev_val,
                category=cat_val,
                file_path=str(f.get("file_path", "unknown")),
                start_line=f.get("start_line"),
                end_line=f.get("end_line"),
                description=str(f.get("description", "")),
                evidence=f.get("evidence"),
                recommendation=f.get("recommendation"),
            )
            findings.append(finding_obj.model_dump())



        # Determine if any critical or high findings block approval
        has_blocking_defects = any(
            f.get("severity") in [ReviewFindingSeverity.CRITICAL.value, ReviewFindingSeverity.HIGH.value]
            for f in findings
        )

        if has_blocking_defects:
            review_status = "CHANGES_REQUESTED"
            next_state = TaskLifecycleState.REVIEW_FAILED.value
        else:
            review_status = "APPROVED"
            next_state = TaskLifecycleState.REVIEW_PASSED.value

        current_review_count = state.get("review_iteration_count", 0)
        next_review_count = current_review_count if review_status == "APPROVED" else current_review_count + 1

        # 2. Persist to DB if session available
        if db is not None and state.get("task_id"):
            try:
                task_id_uuid = uuid.UUID(str(state["task_id"]))
                active_patch_id = state.get("active_patch_id")
                patch_id_uuid = (
                    uuid.UUID(active_patch_id)
                    if active_patch_id is not None and len(active_patch_id) == 36
                    else None
                )



                review_entity = AgentReview(
                    task_id=task_id_uuid,
                    patch_id=patch_id_uuid,
                    status=review_status,
                    summary=summary,
                )
                db.add(review_entity)
                await db.flush()

                for f_data in findings:
                    finding_entity = ReviewFinding(
                        review_id=review_entity.id,
                        severity=f_data["severity"],
                        category=f_data["category"],
                        file_path=f_data["file_path"],
                        start_line=f_data.get("start_line"),
                        end_line=f_data.get("end_line"),
                        description=f_data["description"],
                        evidence=f_data.get("evidence"),
                        recommendation=f_data.get("recommendation"),
                    )
                    db.add(finding_entity)
                await db.flush()
            except Exception as e:
                logger.warning("AgentReview DB persistence error (proceeding in-memory): %s", e)

        return {
            "review_findings": findings,
            "review_status": review_status,
            "review_iteration_count": next_review_count,
            "lifecycle_state": next_state,
            "active_agent": AgentRoleEnum.REVIEWER.value,
            "messages": [
                AIMessage(
                    content=f"Reviewer completed evaluation. Status={review_status}, FindingsCount={len(findings)}.",
                    id=str(uuid.uuid4()),
                )
            ],
        }
