"""Tests for the analyzer pipeline wiring.

These cover the two defects that made AI reviews impossible:

* the pipeline gated analysis on a client that always reported "not
  configured", so agents never ran even with a Gemini key present;
* orchestrator findings were stored without the API ``Issue`` field mapping
  (``suggestion``/``line``), so suggested fixes and line numbers never reached
  the UI.
"""

from __future__ import annotations

from unittest.mock import patch

from app.agents.orchestrator import AgentResult, OrchestratorResult
from app.analyzers import pipeline
from app.schemas.review import ReviewCounts, ReviewResponse
from app.services.review_service import ReviewService

CODE = "def add(a, b):\n    return a / b\n"

FINDING = {
    "id": "div-by-zero",
    "title": "Division by zero is unguarded",
    "description": "b may be 0.",
    "severity": "High",
    "category": "bug",
    "file": "math_utils.py",
    "start_line": 2,
    "end_line": 2,
    "suggested_fix": "if b == 0: raise ValueError",
    "confidence": 0.8,
    "explanation": "ZeroDivisionError at runtime.",
    "source": "ai_suggestion",
    "source_agent": "bug",
}


def test_pipeline_returns_pending_when_gemini_is_not_configured() -> None:
    with patch.object(pipeline, "get_llm_client") as mock_client, patch(
        "app.agents.orchestrator.run_all_agents"
    ) as mock_run:
        mock_client.return_value.is_available = False
        mock_client.return_value.message = "AI analysis is not configured."

        outcome = pipeline.run_analysis(code=CODE, language="python")

    mock_run.assert_not_called()
    assert outcome.status == "pending"
    assert outcome.issues == ()
    assert outcome.quality_score is None


def test_pipeline_runs_agents_when_gemini_is_configured() -> None:
    result = OrchestratorResult(
        status="ok",
        summary="One bug found.",
        findings=[FINDING],
        agent_results=[
            AgentResult(
                agent_id="bug",
                agent_name="Bug Detection Agent",
                status="ok",
                summary="One bug found.",
                findings=[FINDING],
                duration_ms=12,
            )
        ],
        total_duration_ms=42,
        static_tool_findings=0,
        ai_suggestion_findings=1,
    )

    with patch.object(pipeline, "get_llm_client") as mock_client, patch(
        "app.agents.orchestrator.run_all_agents", return_value=result
    ) as mock_run:
        mock_client.return_value.is_available = True

        outcome = pipeline.run_analysis(code=CODE, language="python", filename="math_utils.py")

    mock_run.assert_called_once()
    assert outcome.status == "completed"
    assert outcome.quality_score == 90  # 100 - 10 for High
    assert outcome.duration_ms == 42
    assert len(outcome.issues) == 1

    issue = outcome.issues[0]
    assert issue["suggestion"] == "if b == 0: raise ValueError"
    assert issue["line"] == 2
    assert issue["start_line"] == 2
    assert issue["end_line"] == 2
    assert issue["agent_id"] == "bug"
    assert issue["agent_name"] == "Bug Detection"
    assert issue["source"] == "ai_suggestion"
    assert outcome.agents[0]["findings"] == 1


def test_pipeline_maps_partial_failure_to_completed_with_errors() -> None:
    result = OrchestratorResult(
        status="partial",
        summary="Security agent failed.",
        findings=[],
        agent_results=[
            AgentResult(agent_id="bug", agent_name="Bug Detection Agent", status="ok"),
            AgentResult(
                agent_id="security",
                agent_name="Security Analysis Agent",
                status="error",
                error_message="boom",
            ),
        ],
    )
    with patch.object(pipeline, "get_llm_client") as mock_client, patch(
        "app.agents.orchestrator.run_all_agents", return_value=result
    ):
        mock_client.return_value.is_available = True
        outcome = pipeline.run_analysis(code=CODE, language="python")

    assert outcome.status == "completed_with_errors"


def test_pipeline_failure_reports_error_without_a_score() -> None:
    """A provider outage must never look like a clean 100/100 review."""
    result = OrchestratorResult(
        status="error",
        summary="No review agent completed successfully.",
        findings=[],
        agent_results=[
            AgentResult(
                agent_id="bug",
                agent_name="Bug Detection Agent",
                status="error",
                error_message="Gemini is temporarily unavailable (HTTP 503).",
            )
        ],
    )
    with patch.object(pipeline, "get_llm_client") as mock_client, patch(
        "app.agents.orchestrator.run_all_agents", return_value=result
    ):
        mock_client.return_value.is_available = True
        outcome = pipeline.run_analysis(code=CODE, language="python")

    assert outcome.status == "error"
    assert outcome.quality_score is None
    assert "503" in outcome.message


def test_agent_propagates_service_failure() -> None:
    """Agents raise instead of returning a fake clean result."""
    from app.agents import bug_agent
    from app.llm.gemini_service import GeminiRateLimitError

    class FailingService:
        def analyze(self, **_kwargs):
            raise GeminiRateLimitError("Gemini rate limit reached (HTTP 429).")

    with patch.object(bug_agent, "get_gemini_service", return_value=FailingService()):
        try:
            bug_agent.analyze(CODE, "python")
        except GeminiRateLimitError:
            pass
        else:  # pragma: no cover - the assertion below explains the failure
            raise AssertionError("agent swallowed the Gemini failure")


def test_stored_issues_keep_suggestion_and_line_fields(db_session) -> None:
    """Findings persisted by the service must round-trip through the API model."""
    with patch.object(pipeline, "get_llm_client") as mock_client, patch(
        "app.agents.orchestrator.run_all_agents",
        return_value=OrchestratorResult(
            status="ok",
            summary="One bug found.",
            findings=[FINDING],
            agent_results=[
                AgentResult(
                    agent_id="bug",
                    agent_name="Bug Detection Agent",
                    status="ok",
                    findings=[FINDING],
                )
            ],
        ),
    ):
        mock_client.return_value.is_available = True
        from app.schemas.review import ReviewRequest

        response = ReviewService(db_session).create(
            ReviewRequest(code=CODE, language="python", filename="math_utils.py"),
            user_id="usr_test",
        )

    assert isinstance(response, ReviewResponse)
    assert len(response.issues) == 1
    issue = response.issues[0]
    assert issue.suggestion == "if b == 0: raise ValueError"
    assert issue.line == 2
    assert issue.severity == "High"
    assert response.counts == ReviewCounts(total=1, high=1)
    assert response.grade == "A"  # score 90
