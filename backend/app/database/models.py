"""ORM models for stored review requests and users."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Review(Base):
    """A submitted code review.

    The submitted source is stored for display in the workspace. It is never
    executed by the backend.
    """

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # Owner of the review. Rows created before accounts were enforced have NULL
    # and are not exposed through the API.
    user_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", index=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    fix_decisions: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment=(
            "JSON map of finding_id -> decision (accepted/rejected/muted), "
            "storing user acceptance/rejection of AI fix suggestions."
        ),
    )
    fixed_code: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment=(
            "The code after applying accepted fixes, if any. "
            "Preserves the original code path; only modified when "
            "user explicitly accepts a fix."
        ),
    )
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    agents_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    counts_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base):
    """Application user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    github_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class PasswordResetToken(Base):
    """Password reset token storage."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
