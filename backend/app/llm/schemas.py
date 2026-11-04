"""Structured models for Gemini analysis output.

Model output is untrusted input. Every response is parsed into these models
before anything is handed back to the API layer, so a malformed or partially
populated payload fails validation instead of leaking through.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Severity(str, Enum):
    """Severity levels a finding may use."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class FindingSource(str, Enum):
    """Where a finding came from.

    The backend only treats a finding as confirmed static analysis when a
    deterministic analyzer produced it. Anything the language model reports is
    an AI suggestion.
    """

    STATIC_ANALYSIS = "static_analysis"
    AI_SUGGESTION = "ai_suggestion"


class Finding(BaseModel):
    """A single reported issue in the submitted source code."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    severity: Severity
    category: str = Field(min_length=1, max_length=64)
    file: str = Field(default="", max_length=255)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    suggested_fix: str = Field(min_length=1, max_length=6000)
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How likely the finding is to be a real issue, from 0.0 to 1.0. "
            "A percentage (for example 85) is normalized to 0.85."
        ),
    )
    explanation: str = Field(min_length=1, max_length=4000)
    source: FindingSource = FindingSource.AI_SUGGESTION

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> Any:
        """Accept any casing the model produces, such as ``HIGH`` or ``high``."""
        if isinstance(value, str):
            return value.strip().capitalize()
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> Any:
        """Accept ``0.87`` or ``87``; both mean 87% confidence."""
        if isinstance(value, str):
            try:
                value = float(value.strip().rstrip("%"))
            except ValueError:
                return value
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and 1 < value <= 100:
            return value / 100
        return value

    @field_validator("start_line", "end_line", mode="before")
    @classmethod
    def reject_boolean_line_numbers(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("line numbers must be integers, not booleans.")
        return value

    @model_validator(mode="after")
    def line_range_must_be_ordered(self) -> "Finding":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line.")
        return self


class AgentCategoryAnalysis(BaseModel):
    """One category section of a combined four-category review."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(default="", max_length=2000)
    findings: list[Finding] = Field(default_factory=list)


class GeminiAnalysis(BaseModel):
    """A validated analysis response returned by :class:`GeminiCodeReviewService`."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(default="", max_length=2000)
    findings: list[Finding] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Adjustments made while validating the model output, such as "
            "dropped out-of-range findings."
        ),
    )
    model_name: str | None = None


#: Canonical keys of a combined review. One Gemini request fills all four.
COMBINED_CATEGORY_KEYS: tuple[str, ...] = (
    "bug",
    "security",
    "performance",
    "quality",
)

#: Alternative category names a model may return, mapped to a canonical key.
COMBINED_CATEGORY_ALIASES: dict[str, str] = {
    "bug": "bug",
    "bugs": "bug",
    "bug_detection": "bug",
    "logic": "bug",
    "correctness": "bug",
    "security": "security",
    "security_analysis": "security",
    "vulnerability": "security",
    "performance": "performance",
    "performance_optimization": "performance",
    "perf": "performance",
    "quality": "quality",
    "code_quality": "quality",
    "style": "quality",
    "maintainability": "quality",
}


def normalize_combined_category(value: Any) -> str | None:
    """Map a model-reported category name to a canonical combined key."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    return COMBINED_CATEGORY_ALIASES.get(key)


class CombinedAnalysis(BaseModel):
    """A validated four-category response from a single Gemini request.

    ``categories`` is always populated with all four canonical keys so callers
    can emit one agent result per category without guessing what the model
    returned.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(default="", max_length=2000)
    categories: dict[str, AgentCategoryAnalysis] = Field(
        default_factory=lambda: {
            key: AgentCategoryAnalysis() for key in COMBINED_CATEGORY_KEYS
        }
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Adjustments made while validating the model output, such as "
            "dropped out-of-range findings."
        ),
    )
    model_name: str | None = None
