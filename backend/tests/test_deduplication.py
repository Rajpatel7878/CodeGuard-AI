"""Tests for the cross-agent finding deduplication module.

The deduplicator merges findings that describe the same problem at the same
file location. It keeps the highest-quality representative (highest confidence,
and prefers static_analysis over ai_suggestion when confidence is equal).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.deduplication import deduplicate_findings
from app.llm.schemas import FindingSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _f(
    *,
    id: str = "finding-1",
    category: str = "security",
    file: str = "app.py",
    start_line: int = 10,
    end_line: int = 12,
    confidence: float = 0.8,
    source: str = "ai_suggestion",
    source_agent: str = "security",
    title: str = "A finding",
    description: str = "Some description",
    severity: str = "High",
    suggested_fix: str = "Fix it",
    explanation: str = "Matters because...",
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "file": file,
        "start_line": start_line,
        "end_line": end_line,
        "suggested_fix": suggested_fix,
        "confidence": confidence,
        "explanation": explanation,
        "source": source,
        "source_agent": source_agent,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeduplicateFindings:
    def test_empty_input_returns_empty(self) -> None:
        assert deduplicate_findings([]) == []

    def test_single_finding_passes_through(self) -> None:
        findings = [_f()]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0]["id"] == "finding-1"

    def test_identical_findings_are_merged(self) -> None:
        """Two identical findings should become one."""
        a = _f(id="dup-1", source_agent="bug")
        b = _f(id="dup-1", source_agent="security")
        result = deduplicate_findings([a, b])
        assert len(result) == 1

    def test_merged_finding_tracks_both_source_agents(self) -> None:
        a = _f(id="x", source_agent="bug")
        b = _f(id="x", source_agent="security")
        result = deduplicate_findings([a, b])
        agents = result[0]["source_agents"]
        assert "bug" in agents
        assert "security" in agents

    def test_higher_confidence_wins(self) -> None:
        low = _f(id="a", confidence=0.5, source_agent="bug")
        high = _f(id="b", confidence=0.9, source_agent="security")
        result = deduplicate_findings([low, high])
        assert len(result) == 1
        assert result[0]["confidence"] == pytest.approx(0.9)

    def test_static_analysis_wins_over_ai_when_confidence_equal(self) -> None:
        ai = _f(
            id="ai",
            confidence=0.8,
            source=FindingSource.AI_SUGGESTION.value,
            source_agent="security",
        )
        static = _f(
            id="static",
            confidence=0.8,
            source=FindingSource.STATIC_ANALYSIS.value,
            source_agent="bandit",
        )
        result = deduplicate_findings([ai, static])
        assert len(result) == 1
        assert result[0]["source"] == FindingSource.STATIC_ANALYSIS.value

    def test_different_files_are_not_merged(self) -> None:
        a = _f(file="auth.py", start_line=5, end_line=7)
        b = _f(file="utils.py", start_line=5, end_line=7)
        result = deduplicate_findings([a, b])
        assert len(result) == 2

    def test_different_categories_are_not_merged(self) -> None:
        a = _f(category="security", start_line=5, end_line=7)
        b = _f(category="bug", start_line=5, end_line=7)
        result = deduplicate_findings([a, b])
        assert len(result) == 2

    def test_non_overlapping_lines_are_not_merged(self) -> None:
        a = _f(start_line=1, end_line=5)
        b = _f(start_line=10, end_line=15)
        result = deduplicate_findings([a, b])
        assert len(result) == 2

    def test_overlapping_lines_are_merged(self) -> None:
        a = _f(start_line=1, end_line=8, confidence=0.7)
        b = _f(start_line=5, end_line=12, confidence=0.9)
        result = deduplicate_findings([a, b])
        assert len(result) == 1

    def test_adjacent_lines_do_not_overlap(self) -> None:
        """Lines [1-5] and [6-10] do not overlap — they are adjacent."""
        a = _f(start_line=1, end_line=5)
        b = _f(start_line=6, end_line=10)
        result = deduplicate_findings([a, b])
        assert len(result) == 2

    def test_order_is_preserved_for_non_duplicates(self) -> None:
        a = _f(id="first", start_line=1, end_line=2)
        b = _f(id="second", start_line=20, end_line=22)
        c = _f(id="third", start_line=40, end_line=45)
        result = deduplicate_findings([a, b, c])
        assert [r["id"] for r in result] == ["first", "second", "third"]

    def test_three_way_merge_collects_all_agents(self) -> None:
        a = _f(id="x", source_agent="bug", confidence=0.6)
        b = _f(id="x", source_agent="security", confidence=0.7)
        c = _f(id="x", source_agent="static", confidence=0.8)
        result = deduplicate_findings([a, b, c])
        assert len(result) == 1
        agents = set(result[0]["source_agents"])
        assert agents == {"bug", "security", "static"}

    def test_source_agents_is_always_a_sorted_list(self) -> None:
        a = _f(id="z", source_agent="zebra")
        b = _f(id="z", source_agent="ant")
        result = deduplicate_findings([a, b])
        assert result[0]["source_agents"] == ["ant", "zebra"]

    def test_finding_without_source_agent_key_does_not_crash(self) -> None:
        f = _f()
        del f["source_agent"]
        result = deduplicate_findings([f])
        assert len(result) == 1

    def test_finding_with_enum_source_value(self) -> None:
        """FindingSource enum values should be handled in addition to strings."""
        a = _f(source=FindingSource.AI_SUGGESTION, confidence=0.5)
        b = _f(source=FindingSource.STATIC_ANALYSIS, confidence=0.5)
        result = deduplicate_findings([a, b])
        # static_analysis should win on equal confidence
        assert len(result) == 1
        src = result[0]["source"]
        assert src == FindingSource.STATIC_ANALYSIS or src == FindingSource.STATIC_ANALYSIS.value
