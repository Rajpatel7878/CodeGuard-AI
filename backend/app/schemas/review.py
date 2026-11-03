"""Pydantic request and response schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath

from pydantic import BaseModel, Field, field_validator

from app.schemas.languages import SUPPORTED_LANGUAGES, supported_language_list


class ReviewRequest(BaseModel):
    """Payload accepted by ``POST /api/review``."""

    code: str = Field(description="Source code to review. Never executed by the server.")
    language: str = Field(default="javascript", max_length=32)
    filename: str | None = Field(default=None, max_length=255)

    @field_validator("code")
    @classmethod
    def code_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Code must not be empty.")
        return value

    @field_validator("language")
    @classmethod
    def language_must_be_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language '{value}'. Supported languages: "
                f"{supported_language_list()}."
            )
        return normalized

    @field_validator("filename")
    @classmethod
    def filename_must_be_a_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Store a file name only, never a client path.
        cleaned = value.strip()
        if not cleaned:
            return None
        name = PureWindowsPath(PurePosixPath(cleaned).name).name
        return name or None


class Issue(BaseModel):
    id: str
    agent_id: str | None = None
    agent_name: str | None = None
    severity: str
    title: str
    description: str | None = None
    suggestion: str | None = None
    line: int | None = None
    file: str | None = None
    category: str | None = None
    confidence: float | None = None
    explanation: str | None = None
    source: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    diff: str | None = None
    has_diff: bool = False
    validation_status: str | None = None
    validation_details: str | None = None
    original_finding_id: str | None = None
    original_agent_id: str | None = None


class AgentResult(BaseModel):
    id: str | None = None
    agent_id: str | None = None
    name: str | None = None
    agent_name: str | None = None
    status: str
    findings: int = 0
    duration_ms: int | None = None
    summary: str | None = None
    error_message: str | None = None


class ReviewCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total: int = 0


class ReviewResponse(BaseModel):
    id: str
    status: str
    language: str
    language_label: str
    filename: str | None = None
    lines: int
    characters: int
    quality_score: int | None = None
    grade: str | None = None
    summary: str | None = None
    duration_ms: int | None = None
    created_at: datetime
    code: str
    issues: list[Issue] = Field(default_factory=list)
    agents: list[AgentResult] = Field(default_factory=list)
    counts: ReviewCounts = Field(default_factory=ReviewCounts)
    fix_decisions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of finding_id -> decision (accepted/rejected/muted) for AI fix suggestions",
    )
    fixed_code: str | None = Field(
        default=None,
        description="The code after applying accepted fixes, if any",
    )


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int


class LlmHealth(BaseModel):
    provider: str
    configured: bool
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
    llm: LlmHealth
