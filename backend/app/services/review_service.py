"""Review persistence and response assembly.

Coordinates storage, analysis status, and API representations.
Uses the multi-agent orchestrator for multi-agent review.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analyzers.pipeline import run_analysis
from app.database.models import Review
from app.schemas.languages import language_label
from app.schemas.review import (
    ReviewCounts,
    ReviewListResponse,
    ReviewRequest,
    ReviewResponse,
)

GRADE_THRESHOLDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))

_SEVERITY_FIELDS = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
}


def grade_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _count_issues(issues: list[dict]) -> ReviewCounts:
    counts = ReviewCounts(total=len(issues))
    for issue in issues:
        field = _SEVERITY_FIELDS.get(str(issue.get("severity", "")).strip().lower())
        if field:
            setattr(counts, field, getattr(counts, field) + 1)
    return counts


def _load_json_list(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


class ReviewService:
    """Coordinates storage, analysis status, and API representations.

    Uses the multi-agent orchestrator to coordinate the five specialized review
    agents (Bug Detection, Security Analysis, Performance Optimization, Code
    Quality, and Fix & Validation).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: ReviewRequest, *, user_id: str) -> ReviewResponse:
        outcome = run_analysis(
            code=payload.code,
            language=payload.language,
            filename=payload.filename,
        )

        issues = [dict(issue) for issue in outcome.issues]

        # Fix suggestions start undecided; the user accepts or rejects them.
        fix_decisions = {
            issue["id"]: "pending"
            for issue in issues
            if issue.get("agent_id") == "fix" and issue.get("id")
        }

        status = outcome.status
        if status not in ("pending", "completed", "completed_with_errors", "error"):
            status = "completed"

        agents = [dict(agent) for agent in outcome.agents]
        if not agents:
            # No agent ran. Report all five honestly instead of omitting them.
            from app.agents.registry import build_agent_results

            agents = build_agent_results("pending" if status == "pending" else "skipped")
            for agent in agents:
                agent["agent_id"] = agent["id"]
                agent["agent_name"] = agent["name"]

        review = Review(
            id=f"rev_{uuid4().hex[:12]}",
            user_id=user_id,
            language=payload.language,
            filename=payload.filename,
            code=payload.code,
            status=status,
            summary=outcome.message,
            quality_score=outcome.quality_score,
            duration_ms=outcome.duration_ms,
            fix_decisions=json.dumps(fix_decisions) if fix_decisions else None,
            fixed_code=None,
            issues_json=json.dumps(issues) if issues else None,
            agents_json=json.dumps(agents) if agents else None,
            counts_json=_count_issues(issues).model_dump_json(),
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return self.to_response(review)

    def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        language: str | None = None,
    ) -> ReviewListResponse:
        statement = (
            select(Review)
            .where(Review.user_id == user_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
        )
        count_statement = (
            select(func.count()).select_from(Review).where(Review.user_id == user_id)
        )

        if language:
            normalized = language.strip().lower()
            statement = statement.where(Review.language == normalized)
            count_statement = count_statement.where(Review.language == normalized)

        total = self.db.scalar(count_statement) or 0
        rows = self.db.scalars(statement.limit(limit).offset(offset)).all()

        return ReviewListResponse(
            items=[self.to_response(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(self, review_id: str, *, user_id: str | None = None) -> Review | None:
        review = self.db.get(Review, review_id)
        if review is None:
            return None
        # Reviews belong to the account that created them.
        if user_id is not None and review.user_id != user_id:
            return None
        return review

    def to_response(self, review: Review) -> ReviewResponse:
        fix_decisions: dict[str, str] = {}
        if review.fix_decisions:
            try:
                decoded = json.loads(review.fix_decisions)
                if isinstance(decoded, dict):
                    fix_decisions = decoded
            except json.JSONDecodeError:
                fix_decisions = {}

        issues = _load_json_list(review.issues_json)
        agents = _load_json_list(review.agents_json)

        # Counts are always recomputed from the stored findings so a stale or
        # corrupt counts blob can never misreport the severity breakdown.
        counts = _count_issues(issues)

        return ReviewResponse(
            id=review.id,
            status=review.status,
            language=review.language,
            language_label=language_label(review.language),
            filename=review.filename,
            lines=review.code.count("\n") + 1,
            characters=len(review.code),
            quality_score=review.quality_score,
            grade=grade_for_score(review.quality_score),
            summary=review.summary,
            duration_ms=review.duration_ms,
            created_at=_as_utc(review.created_at),
            code=review.code,
            issues=issues,
            agents=agents,
            counts=counts,
            fix_decisions=fix_decisions,
            fixed_code=review.fixed_code,
        )
