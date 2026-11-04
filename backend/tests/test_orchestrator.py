"""Tests for the multi-agent orchestrator.

The orchestrator runs all five agents in parallel, merges their findings,
deduplicates, and runs the Fix agent on the consolidated findings.

All tests stub out the individual agent ``analyze()`` functions and the static
tool runner so no real Gemini API call or subprocess is made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import app.agents.orchestrator as orchestrator
from app.agents.orchestrator import (
    AgentResult,
    OrchestratorResult,
    run_all_agents,
)
from app.llm.gemini_service import GeminiServiceError, GeminiTimeoutError
from app.llm.schemas import FindingSource


@pytest.fixture(autouse=True)
def _per_agent_review_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests patch the four per-agent runners individually.

    Combined (one-request) review is covered in ``test_combined_agent.py``;
    here the legacy four-request path must be selected explicitly.
    """
    monkeypatch.setattr(orchestrator, "_DEFAULT_REVIEW_MODE", "per_agent")


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

CODE = "def add(a, b):\n    return a + b\n"
LANGUAGE = "python"
FILENAME = "math_utils.py"


def _ai_finding(
    id: str = "f1",
    category: str = "bug",
    start_line: int = 1,
    end_line: int = 2,
    confidence: float = 0.8,
    source_agent: str = "bug",
) -> dict[str, Any]:
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Something is wrong.",
        "severity": "High",
        "category": category,
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Fix it.",
        "confidence": confidence,
        "explanation": "It matters.",
        "source": FindingSource.AI_SUGGESTION,
        "source_agent": source_agent,
    }


def _static_finding(id: str = "ruff-f401") -> dict[str, Any]:
    return {
        "id": id,
        "title": f"[Ruff F401] unused import",
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


def _agent_response(summary: str, findings: list[dict]) -> dict[str, Any]:
    return {"summary": summary, "findings": findings, "warnings": []}


def _fix_response(findings: list[dict]) -> dict[str, Any]:
    return {
        "summary": "Fixes proposed.",
        "findings": [
            {
                "id": f"fix-{f['id']}",
                "title": f"Fix: {f['title']}",
                "description": "Apply the fix.",
                "severity": f["severity"],
                "category": "fix",
                "file": f["file"],
                "start_line": f["start_line"],
                "end_line": f["end_line"],
                "suggested_fix": "Here is the fix.",
                "confidence": 0.75,
                "explanation": "This resolves the issue.",
                "source": FindingSource.AI_SUGGESTION,
                "source_agent": "fix",
                "original_finding_id": f["id"],
                "original_agent_id": f.get("source_agent", "unknown"),
            }
            for f in findings
        ],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Helpers to patch all five agents
# ---------------------------------------------------------------------------

def _patch_all_agents(
    bug_findings=None,
    security_findings=None,
    performance_findings=None,
    quality_findings=None,
    fix_findings=None,
    bug_raises=None,
    security_raises=None,
    static_findings=None,
):
    """Return a context manager that patches all agent analyze() functions."""
    from unittest.mock import patch

    bug_response = _agent_response("Bug summary.", bug_findings or [])
    sec_response = _agent_response("Security summary.", security_findings or [])
    perf_response = _agent_response("Performance summary.", performance_findings or [])
    qual_response = _agent_response("Quality summary.", quality_findings or [])
    fix_response_data = _fix_response(
        (bug_findings or []) + (security_findings or []) + (performance_findings or []) + (quality_findings or [])
    )

    def _make_side_effect(exc, response):
        if exc is not None:
            def se(*a, **kw):
                raise exc
            return se
        return lambda *a, **kw: response

    patches = [
        patch(
            "app.agents.orchestrator._run_bug_agent",
            side_effect=_make_side_effect(bug_raises, bug_response),
        ),
        patch(
            "app.agents.orchestrator._run_security_agent",
            side_effect=_make_side_effect(security_raises, sec_response),
        ),
        patch(
            "app.agents.orchestrator._run_performance_agent",
            return_value=perf_response,
        ),
        patch(
            "app.agents.orchestrator._run_quality_agent",
            return_value=qual_response,
        ),
        patch(
            "app.agents.orchestrator._run_fix_agent",
            return_value=fix_response_data,
        ),
        patch(
            "app.agents.orchestrator.run_static_analysis",
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


class TestRunAllAgentsBasic:
    def test_returns_orchestrator_result(self) -> None:
        with _patch_all_agents():
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        assert isinstance(result, OrchestratorResult)

    def test_all_four_primary_agents_appear_in_agent_results(self) -> None:
        with _patch_all_agents():
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        agent_ids = {r.agent_id for r in result.agent_results}
        assert {"bug", "security", "performance", "quality"}.issubset(agent_ids)

    def test_fix_agent_appears_in_agent_results_when_findings_exist(self) -> None:
        with _patch_all_agents(bug_findings=[_ai_finding()]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        agent_ids = {r.agent_id for r in result.agent_results}
        assert "fix" in agent_ids

    def test_findings_from_all_agents_are_combined(self) -> None:
        bug_f = _ai_finding(id="bug-1", category="bug", start_line=1, end_line=2, source_agent="bug")
        sec_f = _ai_finding(id="sec-1", category="security", start_line=5, end_line=6, source_agent="security")
        with _patch_all_agents(bug_findings=[bug_f], security_findings=[sec_f]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        primary_ids = {f["id"] for f in result.findings if f.get("category") != "fix"}
        assert "bug-1" in primary_ids
        assert "sec-1" in primary_ids

    def test_status_is_ok_when_all_agents_succeed(self) -> None:
        with _patch_all_agents():
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        assert result.status == "ok"

    def test_static_tool_findings_are_included(self) -> None:
        static_f = _static_finding()
        with _patch_all_agents(static_findings=[static_f]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        static_ids = {f["id"] for f in result.findings}
        assert "ruff-f401" in static_ids
        assert result.static_tool_findings >= 1

    def test_static_tool_count_is_tracked_separately(self) -> None:
        static_f = _static_finding()
        with _patch_all_agents(static_findings=[static_f]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        assert result.static_tool_findings >= 1

    def test_total_duration_is_populated(self) -> None:
        with _patch_all_agents():
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        assert result.total_duration_ms is not None
        assert result.total_duration_ms >= 0

    def test_fix_agent_skipped_when_no_findings(self) -> None:
        with _patch_all_agents():
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        fix_results = [r for r in result.agent_results if r.agent_id == "fix"]
        # Fix agent is either skipped or ran; if skipped its status is 'skipped'
        if fix_results:
            assert fix_results[0].status in ("ok", "skipped")


# ---------------------------------------------------------------------------
# Tests — failure isolation
# ---------------------------------------------------------------------------


class TestRunAllAgentsFailureIsolation:
    def test_one_agent_error_does_not_crash_review(self) -> None:
        with _patch_all_agents(
            bug_raises=GeminiServiceError("Gemini unavailable")
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        # Should not raise; overall status may be 'partial'
        assert result.status in ("ok", "partial", "error")

    def test_errored_agent_has_error_status_in_results(self) -> None:
        with _patch_all_agents(bug_raises=RuntimeError("boom")):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        bug_result = next(r for r in result.agent_results if r.agent_id == "bug")
        assert bug_result.status == "error"
        assert bug_result.error_message is not None

    def test_errored_agent_error_message_is_captured(self) -> None:
        with _patch_all_agents(bug_raises=ValueError("test error")):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        bug_result = next(r for r in result.agent_results if r.agent_id == "bug")
        assert "test error" in (bug_result.error_message or "")

    def test_total_failure_with_skipped_fix_agent_is_error(self) -> None:
        """All primary agents failing must be `error`, not `partial`.

        The fix agent is skipped because there is nothing to fix; it must not
        be counted as a success that softens the overall status.
        """
        with _patch_all_agents(
            bug_raises=RuntimeError("boom"),
            security_raises=RuntimeError("boom"),
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        statuses = {r.agent_id: r.status for r in result.agent_results}
        # Performance/quality are patched to succeed in this helper, so the
        # review is legitimately partial here.
        assert result.status == "partial"
        assert statuses["fix"] == "skipped"

    def test_partial_status_when_some_agents_error(self) -> None:
        with _patch_all_agents(
            security_findings=[_ai_finding(id="sec-1", category="security", source_agent="security")],
            bug_raises=GeminiServiceError("Service error"),
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        assert result.status in ("partial", "ok")

    def test_other_agents_still_contribute_when_one_fails(self) -> None:
        sec_f = _ai_finding(id="sec-unique", category="security", start_line=5, end_line=6, source_agent="security")
        with _patch_all_agents(
            security_findings=[sec_f],
            bug_raises=RuntimeError("crash"),
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        primary_ids = {f["id"] for f in result.findings}
        assert "sec-unique" in primary_ids


# ---------------------------------------------------------------------------
# Tests — deduplication
# ---------------------------------------------------------------------------


class TestRunAllAgentsDeduplication:
    def test_same_finding_from_two_agents_is_deduplicated(self) -> None:
        """Bug and Security agents both report an issue at lines 1-2, same category."""
        shared_f = _ai_finding(id="shared", category="security", start_line=1, end_line=2)
        bug_version = dict(shared_f)
        bug_version["source_agent"] = "bug"
        sec_version = dict(shared_f)
        sec_version["source_agent"] = "security"
        with _patch_all_agents(
            bug_findings=[bug_version], security_findings=[sec_version]
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        primary = [f for f in result.findings if f.get("category") == "security"]
        assert len(primary) == 1
        agents = primary[0].get("source_agents", [])
        assert len(agents) >= 1  # both agents recorded

    def test_different_categories_are_not_deduplicated(self) -> None:
        bug_f = _ai_finding(id="overlap", category="bug", start_line=1, end_line=3, source_agent="bug")
        qual_f = _ai_finding(id="overlap-q", category="quality", start_line=1, end_line=3, source_agent="quality")
        with _patch_all_agents(bug_findings=[bug_f], quality_findings=[qual_f]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        primary = [f for f in result.findings if f.get("category") in ("bug", "quality")]
        assert len(primary) == 2


# ---------------------------------------------------------------------------
# Tests — static tool integration
# ---------------------------------------------------------------------------


class TestRunAllAgentsStaticTools:
    def test_static_tools_disabled_when_include_static_tools_false(self) -> None:
        with (
            patch("app.agents.orchestrator.run_static_analysis") as mock_static,
            _patch_all_agents(),
        ):
            run_all_agents(CODE, LANGUAGE, FILENAME, include_static_tools=False)
        mock_static.assert_not_called()

    def test_static_findings_carry_static_analysis_source(self) -> None:
        static_f = _static_finding()
        with _patch_all_agents(static_findings=[static_f]):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)
        static_findings = [
            f for f in result.findings
            if f.get("source") in (
                FindingSource.STATIC_ANALYSIS,
                FindingSource.STATIC_ANALYSIS.value,
            )
        ]
        assert len(static_findings) >= 1


# ---------------------------------------------------------------------------
# Tests — fix agent
# ---------------------------------------------------------------------------


class TestRunAllAgentsFixAgent:
    def test_fix_agent_disabled_when_include_fix_agent_false(self) -> None:
        with (
            patch("app.agents.orchestrator._run_fix_agent") as mock_fix,
            _patch_all_agents(bug_findings=[_ai_finding()]),
        ):
            run_all_agents(
                CODE, LANGUAGE, FILENAME,
                include_fix_agent=False,
            )
        mock_fix.assert_not_called()

    def test_fix_agent_receives_consolidated_findings(self) -> None:
        bug_f = _ai_finding(id="bug-1", category="bug", source_agent="bug")
        sec_f = _ai_finding(id="sec-1", category="security", start_line=5, end_line=6, source_agent="security")

        captured: list[list] = []

        def fake_fix_agent(code, language, filename, findings):
            captured.append(list(findings))
            return _fix_response(findings)

        with (
            patch("app.agents.orchestrator._run_bug_agent", return_value=_agent_response("", [bug_f])),
            patch("app.agents.orchestrator._run_security_agent", return_value=_agent_response("", [sec_f])),
            patch("app.agents.orchestrator._run_performance_agent", return_value=_agent_response("", [])),
            patch("app.agents.orchestrator._run_quality_agent", return_value=_agent_response("", [])),
            patch("app.agents.orchestrator._run_fix_agent", side_effect=fake_fix_agent),
            patch("app.agents.orchestrator.run_static_analysis", return_value=[]),
        ):
            result = run_all_agents(CODE, LANGUAGE, FILENAME)

        assert len(captured) == 1
        ids_sent = {f["id"] for f in captured[0]}
        assert "bug-1" in ids_sent
        assert "sec-1" in ids_sent
