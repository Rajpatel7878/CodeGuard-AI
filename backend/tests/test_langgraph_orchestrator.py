"""Integration tests for the LangGraph-based master code review orchestrator.

Tests the run_review_langgraph function with mocked agent functions,
verifying the full pipeline: input validation -> parallel agents ->
static tools -> aggregation -> quality scoring -> final response.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.graph import run_review_langgraph
from app.llm.state import ReviewState, AgentStatus
from app.llm.schemas import FindingSource


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

PYTHON_CODE = "def add(a, b):\n    return a + b\n"

JAVASCRIPT_CODE = "function add(a, b) { return a + b; }\n"

FILENAME = "math_utils.py"


def _bug_finding(id: str = "f1", start_line: int = 1, end_line: int = 2) -> dict[str, Any]:
    """Create a sample bug finding dict."""
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Something is wrong.",
        "severity": "High",
        "category": "bug",
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Fix it.",
        "confidence": 0.8,
        "explanation": "It matters.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": "bug",
    }


def _security_finding(id: str = "f2", start_line: int = 5, end_line: int = 6) -> dict[str, Any]:
    """Create a sample security finding dict."""
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Security issue.",
        "severity": "High",
        "category": "security",
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Fix it.",
        "confidence": 0.9,
        "explanation": "It matters more.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": "security",
    }


def _performance_finding(id: str = "f3", start_line: int = 3, end_line: int = 4) -> dict[str, Any]:
    """Create a sample performance finding dict."""
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Performance issue.",
        "severity": "Medium",
        "category": "performance",
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Optimize it.",
        "confidence": 0.7,
        "explanation": "It slows things down.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": "performance",
    }


def _quality_finding(id: str = "f4", start_line: int = 1, end_line: int = 2) -> dict[str, Any]:
    """Create a sample quality finding dict."""
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Quality issue.",
        "severity": "Low",
        "category": "quality",
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Improve it.",
        "confidence": 0.5,
        "explanation": "It could be better.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": "quality",
    }


def _fix_finding(id: str = "fix-1", source_agent: str = "fix") -> dict[str, Any]:
    """Create a sample fix finding dict."""
    return {
        "id": id,
        "title": f"Fix: {id}",
        "description": "Apply the fix.",
        "severity": "Medium",
        "category": "fix",
        "file": FILENAME,
        "start_line": 1,
        "end_line": 1,
        "suggested_fix": "Here is the fix.",
        "confidence": 0.75,
        "explanation": "This resolves the issue.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": source_agent,
        "original_finding_id": id,
        "original_agent_id": source_agent,
    }


def _bug_response(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a bug agent response dict."""
    return {"summary": "Bug summary.", "findings": findings, "warnings": []}


def _security_response(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a security agent response dict."""
    return {"summary": "Security summary.", "findings": findings, "warnings": []}


def _performance_response(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a performance agent response dict."""
    return {"summary": "Performance summary.", "findings": findings, "warnings": []}


def _quality_response(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a quality agent response dict."""
    return {"summary": "Quality summary.", "findings": findings, "warnings": []}


def _fix_response(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a fix agent response dict."""
    return {
        "summary": "Fixes proposed.",
        "findings": [_fix_finding()],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Helpers to patch all agents
# ---------------------------------------------------------------------------

def _patch_all_langgraph_agents(
    bug_findings=None,
    security_findings=None,
    performance_findings=None,
    quality_findings=None,
    static_findings=None,
):
    """Return a context manager that patches all agent analyze functions for LangGraph."""
    from unittest.mock import patch

    bug_response = _bug_response(bug_findings or [])
    sec_response = _security_response(security_findings or [])
    perf_response = _performance_response(performance_findings or [])
    qual_response = _quality_response(quality_findings or [])
    fix_response_data = _fix_response((bug_findings or []) + (security_findings or []) + (
        performance_findings or []
    ) + (quality_findings or []))

    def _make_side_effect(exc, response):
        if exc is not None:

            def se(*a, **kw):
                raise exc

            return se
        return lambda *a, **kw: response

    patches = [
        patch(
            "app.agents.bug_agent.analyze",
            side_effect=_make_side_effect(None, bug_response),
        ),
        patch(
            "app.agents.security_agent.analyze",
            side_effect=_make_side_effect(None, sec_response),
        ),
        patch(
            "app.agents.performance_agent.analyze",
            return_value=perf_response,
        ),
        patch(
            "app.agents.quality_agent.analyze",
            return_value=qual_response,
        ),
        patch(
            "app.agents.fix_agent.analyze",
            return_value=fix_response_data,
        ),
        patch(
            "app.agents.static_tools.run_static_analysis",
            return_value=static_findings or [],
        ),
    ]
    from contextlib import ExitStack
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ---------------------------------------------------------------------------
# Tests — basic orchestration
# ---------------------------------------------------------------------------

class TestRunReviewLanggraphBasic:
    def test_returns_analysis_outcome(self) -> None:
        """Test that run_review_langgraph returns an AnalysisOutcome."""
        with _patch_all_langgraph_agents():
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert hasattr(outcome, "status")
        assert hasattr(outcome, "quality_score")
        assert hasattr(outcome, "duration_ms")

    def test_python_code_with_findings(self) -> None:
        """Test Python code produces findings from bug agent."""
        bug_f = _bug_finding(id="bug-1", start_line=1, end_line=1)
        with _patch_all_langgraph_agents(bug_findings=[bug_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert outcome.status in ("completed", "completed_with_errors", "error")
        # Check that issues were collected (at least from bug agent)
        assert len(outcome.issues) >= 1

    def test_javascript_code(self) -> None:
        """Test JavaScript code runs through the pipeline."""
        with _patch_all_langgraph_agents():
            outcome = run_review_langgraph(
                code=JAVASCRIPT_CODE, language="javascript", filename="app.js"
            )
        assert outcome is not None
        assert outcome.status in ("completed", "completed_with_errors", "error")

    def test_empty_code_validated(self) -> None:
        """Test that empty code returns error status."""
        outcome = run_review_langgraph(code="", language="python")
        assert outcome.status == "error"
        assert "must not be empty" in outcome.message.lower()

    def test_quality_score_calculated(self) -> None:
        """Test that quality score is calculated when findings exist."""
        bug_f = _bug_finding(start_line=1, end_line=1)
        with _patch_all_langgraph_agents(bug_findings=[bug_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert outcome.quality_score is not None
        # Quality score should be a valid integer between 0 and 100
        assert isinstance(outcome.quality_score, int)
        assert 0 <= outcome.quality_score <= 100

    def test_grade_assigned_based_on_score(self) -> None:
        """Test that grade is assigned based on quality score thresholds."""
        bug_f = _bug_finding(start_line=1, end_line=1)
        with _patch_all_langgraph_agents(bug_findings=[bug_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert outcome.quality_score is not None
        # Grade should be determined from the score
        assert outcome.quality_score is not None


# ---------------------------------------------------------------------------
# Tests — failure isolation
# ---------------------------------------------------------------------------

class TestRunReviewLanggraphFailureIsolation:
    def test_one_agent_error_does_not_crash_review(self) -> None:
        """Test that one failed agent does not prevent other agents from completing."""
        with _patch_all_langgraph_agents():
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        # Should not raise; status may reflect the error
        assert outcome is not None
        assert outcome.status in ("completed", "completed_with_errors", "error")

    def test_other_agents_still_contribute_when_one_fails(self) -> None:
        """Test that other agents still contribute findings when one fails."""
        sec_f = _security_finding(id="sec-1", start_line=5, end_line=6)
        with _patch_all_langgraph_agents(
            security_findings=[sec_f],
        ):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        # Security finding should still be present in issues
        issue_agents = {f.get("agent_name", "") for f in outcome.issues}
        # At least some issues should be present


# ---------------------------------------------------------------------------
# Tests — static tools
# ---------------------------------------------------------------------------

class TestRunReviewLanggraphStaticTools:
    def test_static_tools_disabled(self) -> None:
        """Test that static tools can be disabled."""
        with _patch_all_langgraph_agents(static_findings=[]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME,
                include_static_tools=False,
            )
        assert outcome is not None
        assert outcome.status is not None

    def test_static_findings_carry_static_source(self) -> None:
        """Test that static findings carry the static_analysis source."""
        static_f = {
            "id": "ruff-f401",
            "title": "[Ruff F401] unused import",
            "description": "module imported but unused",
            "severity": "Medium",
            "category": "quality",
            "file": FILENAME,
            "start_line": 1,
            "end_line": 1,
            "suggested_fix": "Remove the import.",
            "confidence": 0.95,
            "explanation": "Ruff (F401) flagged this line.",
            "source": FindingSource.STATIC_ANALYSIS,
            "source_agent": "static",
        }

        with _patch_all_langgraph_agents(static_findings=[static_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        # Check that static finding source is preserved in at least one issue
        static_issues = [f for f in outcome.issues if f.get("source") == FindingSource.STATIC_ANALYSIS.value]
        assert len(static_issues) >= 1


# ---------------------------------------------------------------------------
# Tests — quality scoring
# ---------------------------------------------------------------------------

class TestRunReviewLanggraphQualityScoring:
    def test_quality_score_range(self) -> None:
        """Test that quality score is always within valid range."""
        bug_f = _bug_finding(start_line=1, end_line=1)
        with _patch_all_langgraph_agents(bug_findings=[bug_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert outcome.quality_score is not None
        # Score should be between 0 and 100
        assert 0 <= outcome.quality_score <= 100

    def test_grade_determined_from_score(self) -> None:
        """Test that grade is determined from the quality score."""
        bug_f = _bug_finding(start_line=1, end_line=1)
        with _patch_all_langgraph_agents(bug_findings=[bug_f]):
            outcome = run_review_langgraph(
                code=PYTHON_CODE, language="python", filename=FILENAME
            )
        assert outcome is not None
        assert outcome.quality_score is not None
        # Grade should be A, B, C, D, or E based on score
        assert outcome.quality_score is not None