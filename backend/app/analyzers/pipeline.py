"""Analysis pipeline — wires the orchestrator to the review service.

The pipeline runs all five specialized agents via the orchestrator, collects
their findings, and returns an :class:`~app.analyzers.base.AnalysisOutcome`.

If Gemini is not configured (no API key) the pipeline returns a ``pending``
outcome without calling any agent, consistent with the Phase-3 behaviour.

The submitted code is **never** executed, imported, or compiled by this module.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analyzers.base import AnalysisOutcome
from app.llm.client import get_llm_client
from app.llm.gemini_service import GeminiNotConfiguredError, GeminiServiceError

logger = logging.getLogger(__name__)

_SEVERITY_DEDUCTIONS = {
    "Critical": 20,
    "High": 10,
    "Medium": 5,
    "Low": 2,
    "Info": 0,
}

_AGENT_NAMES = {
    "bug": "Bug Detection",
    "security": "Security Analysis",
    "performance": "Performance Optimization",
    "quality": "Code Quality",
    "fix": "Fix & Validation",
    "static": "Static Analysis",
}


def _enum_value(value: Any) -> Any:
    """Unwrap an enum (``severity``/``source`` are enums in finding dicts)."""
    return getattr(value, "value", value)


def _to_issue(finding: dict[str, Any], filename: str | None) -> dict[str, Any]:
    """Map an internal finding dict to the API ``Issue`` shape.

    Internal findings use ``suggested_fix``/``start_line``; the API contract
    uses ``suggestion``/``line``. Dropping that mapping meant suggested fixes
    and line numbers never reached the UI.
    """
    start_line = finding.get("start_line")
    end_line = finding.get("end_line")
    source_agent = finding.get("source_agent") or "static"
    severity = str(_enum_value(finding.get("severity")) or "Info").strip()
    source = _enum_value(finding.get("source"))
    confidence = finding.get("confidence")

    return {
        "id": str(finding.get("id") or ""),
        "agent_id": source_agent,
        "agent_name": _AGENT_NAMES.get(source_agent, source_agent),
        "severity": severity,
        "title": str(finding.get("title") or "Issue"),
        "description": finding.get("description"),
        "suggestion": finding.get("suggested_fix") or finding.get("suggestion"),
        "line": start_line,
        "start_line": start_line,
        "end_line": end_line,
        "file": finding.get("file") or filename,
        "category": finding.get("category"),
        "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
        "explanation": finding.get("explanation"),
        "source": str(source) if source is not None else None,
        "diff": finding.get("diff") or None,
        "has_diff": bool(finding.get("has_diff")),
        "validation_status": finding.get("validation_status"),
        "validation_details": finding.get("validation_details"),
        "original_finding_id": finding.get("original_finding_id"),
        "original_agent_id": finding.get("original_agent_id"),
        # Kept for the fix-decision endpoint; ignored by the public Issue schema.
        "updated_code": finding.get("updated_code"),
    }


def run_analysis(*, code: str, language: str, filename: str | None = None) -> AnalysisOutcome:
    """Run the full multi-agent review pipeline on *code*.

    Parameters
    ----------
    code:
        Source code submitted for review. Treated as untrusted data.
    language:
        Language identifier (e.g. ``"python"``).
    filename:
        Optional original file name for display and static-tool routing.

    Returns
    -------
    AnalysisOutcome
        A frozen dataclass with status, message, issues, quality_score, and
        duration_ms.
    """
    # Gate on the real analysis engine. Without a configured key no agent is
    # called and the review is stored as pending rather than fabricated.
    llm = get_llm_client()
    if not llm.is_available:
        return AnalysisOutcome(
            status="pending",
            message=llm.message,
            issues=(),
            quality_score=None,
            duration_ms=None,
            agents=(),
        )

    try:
        from app.agents.orchestrator import run_all_agents

        result = run_all_agents(code=code, language=language, filename=filename)
    except GeminiNotConfiguredError as exc:
        return AnalysisOutcome(
            status="pending",
            message=str(exc),
            issues=(),
            quality_score=None,
            duration_ms=None,
            agents=(),
        )
    except GeminiServiceError as exc:
        return AnalysisOutcome(
            status="error",
            message=f"Code review failed: {exc}",
            issues=(),
            quality_score=None,
            duration_ms=None,
            agents=(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in analysis pipeline")
        return AnalysisOutcome(
            status="error",
            message=f"Unexpected analysis error: {type(exc).__name__}",
            issues=(),
            quality_score=None,
            duration_ms=None,
            agents=(),
        )

    issues = tuple(_to_issue(finding, filename) for finding in result.findings)

    if result.status == "error":
        status = "error"
    elif result.status == "partial":
        status = "completed_with_errors"
    else:
        status = "completed"

    # Only a fully completed review gets a score. Scoring an empty finding list
    # would award 100/100 to a review that never actually ran, and a partial
    # review is scored from incomplete findings.
    quality_score: int | None = None
    if status == "completed":
        # Transparent heuristic score: 100 minus per-finding severity deductions.
        score = 100
        for issue in issues:
            score -= _SEVERITY_DEDUCTIONS.get(str(issue.get("severity")), 0)
        quality_score = max(0, min(100, score))

    agents_payload = []
    for agent_res in result.agent_results:
        agents_payload.append(
            {
                "id": agent_res.agent_id,
                "agent_id": agent_res.agent_id,
                "name": agent_res.agent_name,
                "agent_name": agent_res.agent_name,
                "status": agent_res.status,
                "findings": len(agent_res.findings or []),
                "duration_ms": agent_res.duration_ms,
                "summary": agent_res.summary,
                "error_message": agent_res.error_message,
            }
        )

    summary = result.summary or "Analysis complete."
    if status in ("error", "completed_with_errors") and "Failed:" not in summary:
        details = [
            f"{agent.get('agent_name') or agent.get('agent_id')}: {agent.get('error_message')}"
            for agent in agents_payload
            if agent.get("status") in ("error", "timeout") and agent.get("error_message")
        ]
        if details:
            summary += " Failed: " + "; ".join(details)
    if result.static_tool_findings:
        summary += (
            f" ({result.static_tool_findings} static-tool verified, "
            f"{result.ai_suggestion_findings} AI suggested)"
        )

    return AnalysisOutcome(
        status=status,
        message=summary,
        issues=issues,
        quality_score=quality_score,
        duration_ms=result.total_duration_ms,
        agents=tuple(agents_payload),
    )
