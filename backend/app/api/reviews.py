"""Review submission and history endpoints.

Every endpoint requires an authenticated user, and reviews are scoped to the
account that created them.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database.models import User
from app.database.session import get_db
from app.schemas.review import (
    ReviewListResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.services.review_service import ReviewService

router = APIRouter(tags=["reviews"])

FixDecision = Literal["accepted", "rejected", "muted"]


def _not_found() -> HTTPException:
    # The same response is used for "missing" and "not yours" so a caller
    # cannot probe for review IDs belonging to other accounts.
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Review not found.",
    )


@router.post(
    "/api/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated."},
        413: {"description": "Submitted code exceeds the size limit."},
        422: {"description": "Empty code or unsupported language."},
    },
)
def create_review(
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewResponse:
    if len(payload.code) > settings.max_code_length:
        try:
            status_code = status.HTTP_413_CONTENT_TOO_LARGE
        except AttributeError:  # pragma: no cover - older Starlette releases
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        raise HTTPException(
            status_code=status_code,
            detail=(
                "Code exceeds the maximum length of "
                f"{settings.max_code_length} characters."
            ),
        )
    return ReviewService(db).create(payload, user_id=current_user.id)


@router.post(
    "/api/reviews/{review_id}/fix-decision",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated."},
        404: {"description": "Review or finding not found."},
    },
)
def set_fix_decision(
    review_id: str,
    decision: FixDecision = Query(..., description="Decision: accepted, rejected, or muted"),
    finding_id: str = Query(..., description="Finding ID the decision applies to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewResponse:
    """Record the user's acceptance or rejection of an AI fix suggestion."""
    service = ReviewService(db)
    review = service.get(review_id, user_id=current_user.id)
    if review is None:
        raise _not_found()

    issues: list[dict] = []
    if review.issues_json:
        try:
            decoded = json.loads(review.issues_json)
            if isinstance(decoded, list):
                issues = decoded
        except json.JSONDecodeError:
            issues = []

    issue = next((item for item in issues if item.get("id") == finding_id), None)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found in this review.",
        )

    fix_decisions: dict[str, str] = {}
    if review.fix_decisions:
        try:
            decoded = json.loads(review.fix_decisions)
            if isinstance(decoded, dict):
                fix_decisions = decoded
        except json.JSONDecodeError:
            fix_decisions = {}

    fix_decisions[finding_id] = decision

    # Only an explicit acceptance applies the proposed patch, and only when the
    # Fix agent actually produced updated code. Nothing is invented here.
    if decision == "accepted":
        updated_code = issue.get("updated_code")
        if isinstance(updated_code, str) and updated_code.strip():
            review.fixed_code = updated_code

    review.fix_decisions = json.dumps(fix_decisions)

    try:
        db.add(review)
        db.commit()
        db.refresh(review)
    except Exception:
        db.rollback()
        raise

    return service.to_response(review)


@router.get("/api/reviews", response_model=ReviewListResponse)
def list_reviews(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    language: str | None = Query(default=None, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewListResponse:
    return ReviewService(db).list(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        language=language,
    )


@router.get("/api/reviews/{review_id}", response_model=ReviewResponse)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewResponse:
    service = ReviewService(db)
    review = service.get(review_id, user_id=current_user.id)
    if review is None:
        raise _not_found()
    return service.to_response(review)
