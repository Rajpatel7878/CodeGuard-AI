"""Tests for the quota-efficient combined review mode.

Combined mode asks Gemini once for all four categories (bug, security,
performance, quality) and splits the validated answer into four agent results.
These tests cover:

* a successful combined analysis (one request, four structured agent results);
* malformed / partial model output;
* the HTTP 429 quota-exceeded fallback (no fabricated AI findings, static
  findings preserved, no wasted Fix-agent request).

Every test uses a fake client or fake service, so no network call is made.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import app.agents.orchestrator as orchestrator
from app.agents.combined_agent import COMBINED_CATEGORY_AGENTS
from app.analyzers import pipeline
from app.llm.gemini_service import (
    GeminiCodeReviewService,
    GeminiRateLimitError,
    GeminiResponseError,
    quota_exceeded_message,
)
from app.llm.schemas import (
    COMBINED_CATEGORY_KEYS,
    AgentCategoryAnalysis,
    CombinedAnalysis,
    Finding,
    FindingSource,
)

CODE = "import os\n\ndef add(a, b):\n    return a + b\n"
LANGUAGE = "python"
FILENAME = "math_utils.py"
TOTAL_LINES = CODE.count("\n") + 1
API_KEY = "test-key-should-never-leak"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompt_feedback = None
        self.candidates = []


class FakeModels:
    """Replays prepared responses and records every request."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[SimpleNamespace] = []

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeCombinedService:
    """Stands in for GeminiCodeReviewService in orchestrator-level tests."""

    def __init__(
        self,
        analysis: CombinedAnalysis | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.analysis = analysis
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def analyze_combined(
        self, *, code: str, language: str, filename: str | None = None
    ) -> CombinedAnalysis:
        self.calls.append(
            {"code": code, "language": language, "filename": filename}
        )
        if self.error is not None:
            raise self.error
        assert self.analysis is not None
        return self.analysis


def finding(
    *,
    id: str = "bug-1",
    category: str = "bug",
    start_line: int = 3,
    end_line: int = 4,
    source: str = "ai_suggestion",
) -> dict[str, Any]:
    return {
        "id": id,
        "title": f"Finding {id}",
        "description": "Something is wrong here.",
        "severity": "High",
        "category": category,
        "file": FILENAME,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": "Change the code.",
        "confidence": 0.8,
        "explanation": "It matters.",
        "source": source,
    }


def static_finding() -> dict[str, Any]:
    return {
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


def build_service(outcomes: list[Any]) -> tuple[GeminiCodeReviewService, FakeModels]:
    models = FakeModels(outcomes)
    service = GeminiCodeReviewService(
        api_key=API_KEY,
        timeout_seconds=1.0,
        max_attempts=3,
        client=SimpleNamespace(models=models),
        sleep=lambda _seconds: None,
        random_value=lambda: 0.0,
    )
    return service, models


def combined_payload(
    categories: dict[str, Any] | None = None,
    *,
    summary: str = "Combined review summary.",
) -> str:
    sections: dict[str, Any] = {
        key: {"summary": f"{key} is clean.", "findings": []}
        for key in COMBINED_CATEGORY_KEYS
    }
    sections.update(categories or {})
    return json.dumps({"summary": summary, "categories": sections})


def combined_analysis(
    sections: dict[str, list[dict[str, Any]]] | None = None,
) -> CombinedAnalysis:
    sections = sections or {}
    return CombinedAnalysis(
        summary="Combined review summary.",
        categories={
            key: AgentCategoryAnalysis(
                summary=f"{key} summary.",
                findings=[Finding.model_validate(f) for f in sections.get(key, [])],
            )
            for key in COMBINED_CATEGORY_KEYS
        },
    )


def analyze_combined(service: GeminiCodeReviewService) -> CombinedAnalysis:
    return service.analyze_combined(code=CODE, language=LANGUAGE, filename=FILENAME)


# ---------------------------------------------------------------------------
# Service: successful combined parsing
# ---------------------------------------------------------------------------


class TestCombinedServiceParsing:
    def test_one_request_fills_all_four_categories(self) -> None:
        service, models = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {
                            "bug": {
                                "summary": "One bug.",
                                "findings": [finding(id="bug-1", category="bug")],
                            },
                            "security": {
                                "summary": "One risk.",
                                "findings": [
                                    finding(
                                        id="sec-1",
                                        category="security",
                                        start_line=1,
                                        end_line=1,
                                    )
                                ],
                            },
                        }
                    )
                )
            ]
        )

        analysis = analyze_combined(service)

        # Exactly one Gemini request for all four categories.
        assert len(models.calls) == 1
        assert set(analysis.categories) == set(COMBINED_CATEGORY_KEYS)
        assert [f.id for f in analysis.categories["bug"].findings] == ["bug-1"]
        assert [f.id for f in analysis.categories["security"].findings] == ["sec-1"]
        assert analysis.categories["performance"].findings == []
        assert analysis.categories["quality"].findings == []
        assert analysis.summary == "Combined review summary."
        assert analysis.model_name == service.model
        # Every finding stays an AI suggestion.
        assert analysis.categories["bug"].findings[0].source is FindingSource.AI_SUGGESTION
        assert API_KEY not in models.calls[0].contents

    def test_missing_category_keys_are_reported_as_empty_sections(self) -> None:
        payload = json.dumps(
            {
                "summary": "Only bugs were reported.",
                "categories": {
                    "bug": {"summary": "One bug.", "findings": [finding()]}
                },
            }
        )
        service, _ = build_service([FakeResponse(payload)])

        analysis = analyze_combined(service)

        assert set(analysis.categories) == set(COMBINED_CATEGORY_KEYS)
        for key in ("security", "performance", "quality"):
            assert analysis.categories[key].findings == []

    def test_flat_findings_are_grouped_by_their_category(self) -> None:
        payload = json.dumps(
            {
                "summary": "Mixed findings.",
                "findings": [
                    finding(id="bug-1", category="bug"),
                    finding(id="sec-1", category="security", start_line=1, end_line=1),
                    finding(id="perf-1", category="performance", start_line=2, end_line=2),
                    finding(id="qual-1", category="quality", start_line=3, end_line=3),
                ],
            }
        )
        service, models = build_service([FakeResponse(payload)])

        analysis = analyze_combined(service)

        assert len(models.calls) == 1
        assert [f.id for f in analysis.categories["bug"].findings] == ["bug-1"]
        assert [f.id for f in analysis.categories["security"].findings] == ["sec-1"]
        assert [f.id for f in analysis.categories["performance"].findings] == ["perf-1"]
        assert [f.id for f in analysis.categories["quality"].findings] == ["qual-1"]

    def test_unknown_category_section_is_ignored_with_a_warning(self) -> None:
        service, _ = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {"mystery": {"summary": "?", "findings": []}}
                    )
                )
            ]
        )

        analysis = analyze_combined(service)

        assert set(analysis.categories) == set(COMBINED_CATEGORY_KEYS)
        assert any("mystery" in warning for warning in analysis.warnings)

    def test_mismatched_finding_category_is_filed_under_its_section(self) -> None:
        payload = json.dumps(
            {
                "summary": "Missing authorization.",
                "categories": {
                    "security": {
                        "summary": "One risk.",
                        "findings": [finding(id="sec-1", category="bug")],
                    }
                },
            }
        )
        service, _ = build_service([FakeResponse(payload)])

        analysis = analyze_combined(service)

        result = analysis.categories["security"].findings[0]
        assert result.id == "sec-1"
        assert result.category == "security"
        assert any("filed under 'security'" in warning for warning in analysis.warnings)

    def test_out_of_range_findings_are_dropped_in_combined_mode(self) -> None:
        service, _ = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {
                            "bug": {
                                "summary": "Far away.",
                                "findings": [
                                    finding(
                                        id="far",
                                        start_line=TOTAL_LINES + 10,
                                        end_line=TOTAL_LINES + 12,
                                    )
                                ],
                            }
                        }
                    )
                )
            ]
        )

        analysis = analyze_combined(service)

        assert analysis.categories["bug"].findings == []
        assert any("outside the" in warning for warning in analysis.warnings)

    def test_duplicate_ids_across_categories_are_made_unique(self) -> None:
        service, _ = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {
                            "bug": {"summary": "b", "findings": [finding(id="same")]},
                            "security": {
                                "summary": "s",
                                "findings": [
                                    finding(
                                        id="same",
                                        category="security",
                                        start_line=1,
                                        end_line=1,
                                    )
                                ],
                            },
                        }
                    )
                )
            ]
        )

        analysis = analyze_combined(service)

        bug_id = analysis.categories["bug"].findings[0].id
        security_id = analysis.categories["security"].findings[0].id
        assert (bug_id, security_id) == ("same", "same-2")
        assert any("Duplicate finding id" in warning for warning in analysis.warnings)

    def test_model_static_analysis_label_is_downgraded(self) -> None:
        service, _ = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {
                            "quality": {
                                "summary": "q",
                                "findings": [finding(source="static_analysis")],
                            }
                        }
                    )
                )
            ]
        )

        analysis = analyze_combined(service)

        result = analysis.categories["quality"].findings[0]
        assert result.source is FindingSource.AI_SUGGESTION
        assert any("static_analysis" in warning for warning in analysis.warnings)


# ---------------------------------------------------------------------------
# Service: malformed responses
# ---------------------------------------------------------------------------


class TestCombinedServiceMalformedResponses:
    def test_malformed_json_is_reported(self) -> None:
        service, _ = build_service([FakeResponse("definitely not json")])

        with pytest.raises(GeminiResponseError, match="malformed JSON"):
            analyze_combined(service)

    def test_missing_categories_object_is_reported(self) -> None:
        service, _ = build_service(
            [FakeResponse(json.dumps({"summary": "no categories here"}))]
        )

        with pytest.raises(GeminiResponseError, match="categories"):
            analyze_combined(service)

    def test_invalid_finding_in_a_section_fails_validation(self) -> None:
        broken = finding()
        del broken["title"]
        service, _ = build_service(
            [
                FakeResponse(
                    combined_payload(
                        {"bug": {"summary": "b", "findings": [broken]}}
                    )
                )
            ]
        )

        with pytest.raises(GeminiResponseError, match="failed validation") as error:
            analyze_combined(service)

        assert "title" in str(error.value)

    def test_categories_that_are_not_an_object_are_rejected(self) -> None:
        service, _ = build_service(
            [FakeResponse(json.dumps({"summary": "x", "categories": ["bug"]}))]
        )

        with pytest.raises(GeminiResponseError, match="categories"):
            analyze_combined(service)


# ---------------------------------------------------------------------------
# Orchestrator: combined mode
# ---------------------------------------------------------------------------


class TestCombinedModeOrchestration:
    def test_one_request_yields_four_agent_results(self) -> None:
        fake_service = FakeCombinedService(
            analysis=combined_analysis(
                {
                    "bug": [finding(id="bug-1")],
                    "quality": [
                        finding(
                            id="qual-1",
                            category="quality",
                            start_line=1,
                            end_line=1,
                        )
                    ],
                }
            )
        )

        with (
            patch(
                "app.agents.combined_agent.get_gemini_service",
                return_value=fake_service,
            ),
            patch.object(orchestrator, "run_static_analysis", return_value=[]),
        ):
            result = orchestrator.run_all_agents(
                CODE,
                LANGUAGE,
                FILENAME,
                review_mode="combined",
                include_fix_agent=False,
            )

        assert len(fake_service.calls) == 1
        assert result.status == "ok"
        assert [r.agent_id for r in result.agent_results] == [
            "bug",
            "security",
            "performance",
            "quality",
        ]
        assert all(r.status == "ok" for r in result.agent_results)

        by_agent = {r.agent_id: r for r in result.agent_results}
        assert [f["id"] for f in by_agent["bug"].findings] == ["bug-1"]
        assert [f["id"] for f in by_agent["quality"].findings] == ["qual-1"]
        assert by_agent["bug"].findings[0]["source_agent"] == "bug"
        assert by_agent["quality"].findings[0]["source_agent"] == "quality"
        assert result.ai_suggestion_findings == 2
        assert result.static_tool_findings == 0

    def test_fix_agent_still_runs_after_a_combined_review(self) -> None:
        fake_service = FakeCombinedService(
            analysis=combined_analysis({"bug": [finding(id="bug-1")]})
        )
        captured: list[list[dict[str, Any]]] = []

        def fake_fix(code, language, filename, findings):
            captured.append(list(findings))
            return {
                "summary": "Fix proposed.",
                "findings": [
                    {
                        "id": "fix-bug-1",
                        "title": "Fix: guard the input",
                        "description": "Add a guard.",
                        "severity": "High",
                        "category": "fix",
                        "file": FILENAME,
                        "start_line": 3,
                        "end_line": 4,
                        "suggested_fix": "if b == 0: raise ValueError",
                        "confidence": 0.7,
                        "explanation": "Prevents a crash.",
                        "source": FindingSource.AI_SUGGESTION,
                        "source_agent": "fix",
                    }
                ],
                "warnings": [],
            }

        with (
            patch(
                "app.agents.combined_agent.get_gemini_service",
                return_value=fake_service,
            ),
            patch.object(orchestrator, "run_static_analysis", return_value=[]),
            patch.object(orchestrator, "_run_fix_agent", side_effect=fake_fix),
        ):
            result = orchestrator.run_all_agents(
                CODE, LANGUAGE, FILENAME, review_mode="combined"
            )

        # One combined request, and the Fix agent received the findings.
        assert len(fake_service.calls) == 1
        assert len(captured) == 1
        assert {f["id"] for f in captured[0]} == {"bug-1"}
        fix_results = [r for r in result.agent_results if r.agent_id == "fix"]
        assert len(fix_results) == 1
        assert fix_results[0].status == "ok"

    def test_malformed_response_fails_all_four_agents_without_fabricating(self) -> None:
        fake_service = FakeCombinedService(
            error=GeminiResponseError(
                "Gemini returned malformed JSON, so no findings could be read."
            )
        )

        with (
            patch(
                "app.agents.combined_agent.get_gemini_service",
                return_value=fake_service,
            ),
            patch.object(orchestrator, "run_static_analysis", return_value=[static_finding()]),
            patch.object(orchestrator, "_run_fix_agent", return_value={
                "summary": "No fixes.",
                "findings": [],
                "warnings": [],
            }) as mock_fix,
        ):
            result = orchestrator.run_all_agents(
                CODE, LANGUAGE, FILENAME, review_mode="combined"
            )

        primary = [r for r in result.agent_results if r.agent_id in COMBINED_CATEGORY_AGENTS]
        assert len(primary) == 4
        assert all(r.status == "error" for r in primary)
        assert all("malformed JSON" in (r.error_message or "") for r in primary)
        assert all(r.findings == [] for r in primary)

        # No AI findings were invented; the Ruff finding survived.
        assert result.ai_suggestion_findings == 0
        assert [f["id"] for f in result.findings] == ["ruff-f401"]
        assert result.static_tool_findings == 1
        # The four AI agents failed, but the Fix agent did complete, so the
        # review is honestly reported as partial rather than a clean success.
        assert result.status == "partial"
        assert "malformed JSON" in result.summary
        # The Fix agent workflow is unchanged for non-quota failures.
        mock_fix.assert_called_once()

    def test_per_agent_mode_still_issues_four_requests(self) -> None:
        def empty(code, language, filename):
            return {"summary": "clean", "findings": [], "warnings": []}

        with (
            patch.object(orchestrator, "_run_bug_agent", side_effect=empty) as bug,
            patch.object(orchestrator, "_run_security_agent", side_effect=empty) as security,
            patch.object(orchestrator, "_run_performance_agent", side_effect=empty) as performance,
            patch.object(orchestrator, "_run_quality_agent", side_effect=empty) as quality,
            patch.object(orchestrator, "run_static_analysis", return_value=[]),
        ):
            result = orchestrator.run_all_agents(
                CODE,
                LANGUAGE,
                FILENAME,
                review_mode="per_agent",
                include_fix_agent=False,
            )

        assert [bug.call_count, security.call_count, performance.call_count, quality.call_count] == [
            1,
            1,
            1,
            1,
        ]
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# Orchestrator + pipeline: quota-exceeded fallback
# ---------------------------------------------------------------------------


class TestQuotaExceededFallback:
    def test_quota_error_fails_agents_and_skips_the_fix_agent(self) -> None:
        message = quota_exceeded_message("gemini-3.8-flash")
        fake_service = FakeCombinedService(error=GeminiRateLimitError(message))

        with (
            patch(
                "app.agents.combined_agent.get_gemini_service",
                return_value=fake_service,
            ),
            patch.object(orchestrator, "run_static_analysis", return_value=[static_finding()]),
            patch.object(orchestrator, "_run_fix_agent") as mock_fix,
        ):
            result = orchestrator.run_all_agents(
                CODE, LANGUAGE, FILENAME, review_mode="combined"
            )

        # Exactly one Gemini call, and no Fix-agent request against a dead quota.
        assert len(fake_service.calls) == 1
        mock_fix.assert_not_called()

        primary = [r for r in result.agent_results if r.agent_id in COMBINED_CATEGORY_AGENTS]
        assert all(r.status == "error" for r in primary)
        assert all("quota exceeded" in (r.error_message or "") for r in primary)
        assert all("429" in (r.error_message or "") for r in primary)
        assert all(r.findings == [] for r in primary)

        fix_results = [r for r in result.agent_results if r.agent_id == "fix"]
        assert len(fix_results) == 1
        assert fix_results[0].status == "skipped"
        assert "quota" in (fix_results[0].summary or "").lower()

        # Static findings are preserved and no AI finding is fabricated.
        assert [f["id"] for f in result.findings] == ["ruff-f401"]
        assert result.static_tool_findings == 1
        assert result.ai_suggestion_findings == 0
        assert result.status == "error"
        assert "quota exceeded" in result.summary
        # The shared failure reason is stated once, not four times.
        assert result.summary.count("quota exceeded") == 1

    def test_pipeline_keeps_static_findings_and_reports_quota_error(self) -> None:
        message = quota_exceeded_message("gemini-3.8-flash")
        fake_service = FakeCombinedService(error=GeminiRateLimitError(message))

        with (
            patch.object(pipeline, "get_llm_client") as mock_client,
            patch(
                "app.agents.combined_agent.get_gemini_service",
                return_value=fake_service,
            ),
            patch.object(orchestrator, "run_static_analysis", return_value=[static_finding()]),
            patch.object(orchestrator, "_run_fix_agent") as mock_fix,
        ):
            mock_client.return_value.is_available = True
            mock_client.return_value.message = "Gemini analysis is enabled."

            outcome = pipeline.run_analysis(
                code=CODE, language=LANGUAGE, filename=FILENAME
            )

        mock_fix.assert_not_called()
        assert outcome.status == "error"
        assert outcome.quality_score is None
        assert "quota exceeded" in outcome.message
        assert len(outcome.issues) == 1
        assert outcome.issues[0]["id"] == "ruff-f401"
        assert outcome.issues[0]["source"] == FindingSource.STATIC_ANALYSIS.value
        # Four AI agents are reported as errored, never as successes.
        primary_agents = [
            agent for agent in outcome.agents if agent["id"] in COMBINED_CATEGORY_AGENTS
        ]
        assert len(primary_agents) == 4
        assert all(agent["status"] == "error" for agent in primary_agents)
