"""Cross-agent finding deduplication.

After all five agents have run, their findings are merged. Without
deduplication the same issue (e.g. an SQL injection found by both the Bug
agent and the Security agent) would appear twice in the report.

Strategy
--------
Two findings are considered duplicates when they share:

1. The same **file** and overlapping **line range**, AND
2. The same top-level **category** (bug, security, performance, quality, fix).

When duplicates are found the one with the higher confidence is kept. If they
have equal confidence the one with the higher-priority source is kept
(``static_analysis`` > ``ai_suggestion``).

The ``source_agents`` list on the surviving finding is extended so the
front-end can show which agents spotted the issue.

Usage
-----
::

    from app.agents.deduplication import deduplicate_findings

    merged = deduplicate_findings(all_findings_from_all_agents)

Each element of the input list is a plain ``dict`` as returned by
``Finding.model_dump()``. An extra key ``"source_agent"`` (str) is expected so
the deduplicator can track provenance.
"""

from __future__ import annotations

import logging
from typing import Any

from app.llm.schemas import FindingSource

logger = logging.getLogger(__name__)

# Source priority: static_analysis beats ai_suggestion
_SOURCE_PRIORITY: dict[str, int] = {
    FindingSource.STATIC_ANALYSIS.value: 2,
    FindingSource.AI_SUGGESTION.value: 1,
}


def _source_priority(finding: dict[str, Any]) -> int:
    source = finding.get("source")
    if isinstance(source, FindingSource):
        return _SOURCE_PRIORITY.get(source.value, 0)
    return _SOURCE_PRIORITY.get(str(source), 0)


def _lines_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True when the line ranges of *a* and *b* overlap."""
    a_start = int(a.get("start_line") or 1)
    a_end = int(a.get("end_line") or a_start)
    b_start = int(b.get("start_line") or 1)
    b_end = int(b.get("end_line") or b_start)
    # Overlap when one range starts before the other ends
    return a_start <= b_end and b_start <= a_end


def _same_file(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("file") or "").strip().lower() == (b.get("file") or "").strip().lower()


def _same_category(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("category") or "").strip().lower() == (b.get("category") or "").strip().lower()


def _are_duplicates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True when *a* and *b* are substantively the same finding."""
    return _same_file(a, b) and _same_category(a, b) and _lines_overlap(a, b)


def _better(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
    """Return True when *candidate* should replace *incumbent*."""
    cand_conf = float(candidate.get("confidence") or 0.0)
    inc_conf = float(incumbent.get("confidence") or 0.0)
    if cand_conf != inc_conf:
        return cand_conf > inc_conf
    return _source_priority(candidate) > _source_priority(incumbent)


def deduplicate_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate findings, keeping the highest-quality representative.

    Each finding dict may have an optional ``"source_agent"`` key (str). The
    returned dicts carry a ``"source_agents"`` list (always a list) tracking
    every agent that reported the finding.

    The output list preserves insertion order of the surviving representative.
    """
    # Each slot: (representative_finding, set_of_source_agents)
    groups: list[tuple[dict[str, Any], set[str]]] = []

    for incoming in findings:
        agent_label = str(incoming.get("source_agent") or "unknown")
        matched = False

        for idx, (rep, agents) in enumerate(groups):
            if _are_duplicates(incoming, rep):
                # Merge the source agent list
                agents.add(agent_label)
                # Replace representative if incoming is higher quality
                if _better(incoming, rep):
                    new_rep = dict(incoming)
                    groups[idx] = (new_rep, agents)
                matched = True
                break

        if not matched:
            groups.append((dict(incoming), {agent_label}))

    result: list[dict[str, Any]] = []
    for rep, agents in groups:
        rep = dict(rep)
        rep.setdefault("source_agents", [])
        existing: list[str] = list(rep.get("source_agents") or [])
        merged_agents = sorted(set(existing) | agents)
        rep["source_agents"] = merged_agents
        result.append(rep)

    original_count = len(findings)
    deduped_count = len(result)
    if original_count != deduped_count:
        logger.info(
            "Deduplication: %d finding(s) merged into %d unique finding(s).",
            original_count,
            deduped_count,
        )

    return result
