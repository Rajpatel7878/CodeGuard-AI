"""Quota-efficient combined review: one Gemini request, four agent results.

Running Bug Detection, Security Analysis, Performance Optimization, and Code
Quality as four independent Gemini requests costs four units of quota per
review. On a free-tier key that limit is reached quickly, and every agent then
fails on its own with HTTP 429.

This module asks Gemini once, with the combined system instruction, and splits
the validated answer into the four canonical categories. The orchestrator turns
each category into the same ``AgentResult`` shape the per-agent mode produces,
so the API response and the frontend agent breakdown are unchanged.

The submitted code is only ever prompt text: it is never executed, imported, or
evaluated. Findings stay labeled ``ai_suggestion``; this module never claims
static verification.
"""

from __future__ import annotations

import logging
from typing import Any

from app.llm.gemini_service import GeminiServiceError
from app.llm.provider import get_review_service as _get_review_service
from app.llm.schemas import (
    COMBINED_CATEGORY_KEYS,
    Finding,
    FindingSource,
)

logger = logging.getLogger(__name__)

# Provider-neutral getter (OpenRouter or Gemini). The historical name is kept
# so existing tests and callers can still patch this module attribute.
# Overridable in tests via monkeypatch.setattr(combined_agent, "get_gemini_service", ...)
get_gemini_service = _get_review_service

#: Category key → (agent id, agent name) as reported by the orchestrator.
COMBINED_CATEGORY_AGENTS: dict[str, tuple[str, str]] = {
    "bug": ("bug", "Bug Detection Agent"),
    "security": ("security", "Security Analysis Agent"),
    "performance": ("performance", "Performance Optimization Agent"),
    "quality": ("quality", "Code Quality Agent"),
}

def _normalize_findings(
    findings: list[Finding], agent_id: str
) -> list[dict[str, Any]]:
    """Normalize section findings into the shared finding dict shape."""
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        normalized.append(
            Finding(
                id=finding.id,
                title=finding.title,
                description=finding.description,
                severity=finding.severity,
                category=finding.category or agent_id,
                file=finding.file or "submitted_code",
                start_line=finding.start_line,
                end_line=finding.end_line,
                suggested_fix=finding.suggested_fix,
                confidence=finding.confidence,
                explanation=finding.explanation,
                source=FindingSource.AI_SUGGESTION,
            ).model_dump()
            | {"source_agent": agent_id}
        )
    return normalized


def analyze(
    code: str,
    language: str,
    filename: str | None = None,
) -> dict[str, Any]:
    """Run one combined review and return per-category results.

    Returns
    -------
    dict
        ``{"summary": str, "categories": {category: {"summary": str,
        "findings": list[dict]}}, "warnings": list[str]}`` with all four
        canonical category keys present.

    Raises
    ------
    GeminiServiceError
        On any provider or response failure. Callers must record the four
        agents as failed rather than reporting clean, empty results.
    """
    try:
        service = get_gemini_service()
        result = service.analyze_combined(
            code=code, language=language, filename=filename
        )
    except GeminiServiceError:
        # Never turn a failure into a clean, empty review.
        raise

    categories: dict[str, dict[str, Any]] = {}
    for key in COMBINED_CATEGORY_KEYS:
        section = result.categories.get(key)
        agent_id = COMBINED_CATEGORY_AGENTS[key][0]
        categories[key] = {
            "summary": section.summary if section else "",
            "findings": _normalize_findings(list(section.findings) if section else [], agent_id),
        }

    return {
        "summary": result.summary,
        "categories": categories,
        "warnings": list(result.warnings),
    }
