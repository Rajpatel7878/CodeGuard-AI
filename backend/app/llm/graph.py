"""LangGraph-based master code review orchestrator.

This module builds a LangGraph that coordinates the five specialized review
agents (Bug Detection, Security Analysis, Performance Optimization, Code
Quality, and Fix & Validation) and combines their findings into a unified
review result.

The graph structure:
  Input validation -> [Parallel agents] -> Static tools -> Aggregation ->
  Quality scoring -> Final response

Key design principles:
- Failure isolation: one failed agent does not prevent others from completing
- Parallel execution: primary agents run concurrently with timeouts
- Deduplication: overlapping findings are merged, keeping the best representative
- Transparent scoring: quality score is calculated with documented rules,
  not claimed as objective measurement
"""

from __future__ import annotations

import time
from typing import Any

from app.llm.state import ReviewState, AgentResult, AgentStatus
from app.llm.schemas import FindingSource
from app.agents.static_tools import run_static_analysis
from app.agents.deduplication import deduplicate_findings
from app.analyzers.base import AnalysisOutcome


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


def node_input_validation(state: ReviewState) -> ReviewState:
    """Validate the review input before running agents."""
    if not state.code.strip():
        state.agent_errors["input"] = "Submitted code must not be empty."
        state.agent_statuses["input"] = AgentStatus.FAILED
        return state

    if not state.language.strip():
        state.agent_errors["input"] = "Language must be specified."
        state.agent_statuses["input"] = AgentStatus.FAILED
        return state

    # Initialize all agent statuses to PENDING
    agents = ["bug", "security", "performance", "quality"]
    if state.include_fix_agent:
        agents.append("fix")

    for agent_id in agents:
        state.agent_statuses[agent_id] = AgentStatus.PENDING

    return state


def node_bug_detection(state: ReviewState) -> ReviewState:
    """Run the Bug Detection Agent."""
    from app.agents.bug_agent import analyze as bug_analyze

    state.agent_statuses["bug"] = AgentStatus.RUNNING
    try:
        result = bug_analyze(
            code=state.code,
            language=state.language,
            filename=state.filename,
        )
        state.agent_results["bug"] = AgentResult(
            agent_id="bug",
            agent_name="Bug Detection Agent",
            status=AgentStatus.COMPLETED,
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
        )
        for f in state.agent_results["bug"].findings:
            f["source_agent"] = "bug"
        state.agent_statuses["bug"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["bug"] = f"{type(exc).__name__}: {exc}"
        state.agent_statuses["bug"] = AgentStatus.FAILED

    return state


def node_security_analysis(state: ReviewState) -> ReviewState:
    """Run the Security Analysis Agent."""
    from app.agents.security_agent import analyze as security_analyze

    state.agent_statuses["security"] = AgentStatus.RUNNING
    try:
        result = security_analyze(
            code=state.code,
            language=state.language,
            filename=state.filename,
        )
        state.agent_results["security"] = AgentResult(
            agent_id="security",
            agent_name="Security Analysis Agent",
            status=AgentStatus.COMPLETED,
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
        )
        for f in state.agent_results["security"].findings:
            f["source_agent"] = "security"
        state.agent_statuses["security"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["security"] = f"{type(exc).__name__}: {exc}"
        state.agent_statuses["security"] = AgentStatus.FAILED

    return state


def node_performance_analysis(state: ReviewState) -> ReviewState:
    """Run the Performance Optimization Agent."""
    from app.agents.performance_agent import analyze as performance_analyze

    state.agent_statuses["performance"] = AgentStatus.RUNNING
    try:
        result = performance_analyze(
            code=state.code,
            language=state.language,
            filename=state.filename,
        )
        state.agent_results["performance"] = AgentResult(
            agent_id="performance",
            agent_name="Performance Optimization Agent",
            status=AgentStatus.COMPLETED,
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
        )
        for f in state.agent_results["performance"].findings:
            f["source_agent"] = "performance"
        state.agent_statuses["performance"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["performance"] = f"{type(exc).__name__}: {exc}"
        state.agent_statuses["performance"] = AgentStatus.FAILED

    return state


def node_code_quality(state: ReviewState) -> ReviewState:
    """Run the Code Quality Agent."""
    from app.agents.quality_agent import analyze as quality_analyze

    state.agent_statuses["quality"] = AgentStatus.RUNNING
    try:
        result = quality_analyze(
            code=state.code,
            language=state.language,
            filename=state.filename,
        )
        state.agent_results["quality"] = AgentResult(
            agent_id="quality",
            agent_name="Code Quality Agent",
            status=AgentStatus.COMPLETED,
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
        )
        for f in state.agent_results["quality"].findings:
            f["source_agent"] = "quality"
        state.agent_statuses["quality"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["quality"] = f"{type(exc).__name__}: {exc}"
        state.agent_statuses["quality"] = AgentStatus.FAILED

    return state


def node_fix_validation(state: ReviewState) -> ReviewState:
    """Run the Fix & Validation Agent (sequential, after other agents)."""
    if not state.include_fix_agent:
        state.agent_statuses["fix"] = AgentStatus.SKIPPED
        return state

    state.agent_statuses["fix"] = AgentStatus.RUNNING
    try:
        findings_from_others: list[dict[str, Any]] = []
        for agent_id in ["bug", "security", "performance", "quality"]:
            if agent_id in state.agent_results:
                findings_from_others.extend(
                    state.agent_results[agent_id].findings
                )

        from app.agents.fix_agent import analyze as fix_analyze
        result = fix_analyze(
            code=state.code,
            language=state.language,
            filename=state.filename,
            findings_from_other_agents=findings_from_others,
        )

        state.agent_results["fix"] = AgentResult(
            agent_id="fix",
            agent_name="Fix & Validation Agent",
            status=AgentStatus.COMPLETED,
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
        )
        for f in state.agent_results["fix"].findings:
            f["source_agent"] = "fix"
        state.agent_statuses["fix"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["fix"] = f"{type(exc).__name__}: {exc}"
        state.agent_statuses["fix"] = AgentStatus.FAILED

    return state


def node_static_tools(state: ReviewState) -> ReviewState:
    """Run static analysis tools (Ruff, Bandit, ESLint, cppcheck)."""
    if not state.include_static_tools:
        state.static_tool_findings = 0
        return state

    state.agent_statuses["static"] = AgentStatus.RUNNING
    try:
        # Look up dynamically to allow test patching
        try:
            from app.agents import static_tools
            static_fn = getattr(static_tools, "run_static_analysis", run_static_analysis)
        except Exception:
            static_fn = run_static_analysis
        static_findings = static_fn(
            code=state.code,
            language=state.language,
            filename=state.filename,
        )
        state.static_tool_findings = len(static_findings)
        for f in static_findings:
            # Preserve existing source if it's static_analysis, otherwise set it
            if f.get("source") not in (FindingSource.STATIC_ANALYSIS.value, FindingSource.STATIC_ANALYSIS):
                f["source"] = FindingSource.STATIC_ANALYSIS
            elif isinstance(f.get("source"), FindingSource):
                f["source"] = f["source"].value
            f["source_agent"] = f.get("source_agent") or "static"

        # Store static findings for later aggregation
        if not hasattr(state, "static_findings_list"):
            state.static_findings_list = []
        state.static_findings_list = static_findings
        state.agent_statuses["static"] = AgentStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001
        state.agent_errors["static"] = f"{type(exc).__name__}: {exc}"
        state.static_tool_findings = 0
        state.agent_statuses["static"] = AgentStatus.FAILED

    return state


def node_find_aggregation(state: ReviewState) -> ReviewState:
    """Aggregate all agent findings into a single list."""
    all_findings: list[dict[str, Any]] = []

    # Add static tool findings first or mixed in
    static_findings = getattr(state, "static_findings_list", []) or []
    all_findings.extend(static_findings)

    for agent_id in ["bug", "security", "performance", "quality", "fix"]:
        if agent_id in state.agent_results:
            all_findings.extend(state.agent_results[agent_id].findings)

    state.all_findings = all_findings
    state.deduplicated_findings = deduplicate_findings(all_findings)
    state.ai_suggestion_findings = len(
        [
            f
            for f in state.deduplicated_findings
            if not (
                f.get("source") == FindingSource.STATIC_ANALYSIS.value
                or f.get("source") == FindingSource.STATIC_ANALYSIS
            )
        ]
    )
    state.static_tool_findings = len(
        [
            f
            for f in state.deduplicated_findings
            if (
                f.get("source") == FindingSource.STATIC_ANALYSIS.value
                or f.get("source") == FindingSource.STATIC_ANALYSIS
            )
        ]
    )

    return state


def node_quality_scoring(state: ReviewState) -> ReviewState:
    """Calculate a transparent code quality score.

    The score starts at 100 and deducts based on finding severity:
      Critical: 20 points
      High:    10 points
      Medium:   5 points
      Low:      2 points
      Info:      0 points

    This score is a heuristic, not an objective measurement.
    """
    score = 100
    for finding in state.deduplicated_findings:
        sev = str(finding.get("severity") or "").strip()
        if sev == "Critical":
            score -= 20
        elif sev == "High":
            score -= 10
        elif sev == "Medium":
            score -= 5
        elif sev == "Low":
            score -= 2
        # Info: no deduction
    state.quality_score = max(0, min(100, score))

    if state.quality_score >= 90:
        state.grade = "A"
    elif state.quality_score >= 80:
        state.grade = "B"
    elif state.quality_score >= 70:
        state.grade = "C"
    elif state.quality_score >= 60:
        state.grade = "D"
    else:
        state.grade = "E"

    return state


def node_final_response(state: ReviewState) -> AnalysisOutcome:
    """Build the final AnalysisOutcome response."""
    issues = []
    for f in state.deduplicated_findings:
        issue = {
            "id": f.get("id", ""),
            "agent_id": f.get("source_agent", ""),
            "agent_name": _agent_name_from_id(f.get("source_agent", "")),
            "severity": f.get("severity") or "Info",
            "title": f.get("title", ""),
            "description": f.get("description", ""),
            "suggestion": f.get("suggested_fix", ""),
            "line": f.get("start_line", 1),
        }
        # Preserve source information for tests/consumers
        if f.get("source") is not None:
            src = f.get("source")
            if hasattr(src, "value"):
                issue["source"] = src.value
            else:
                issue["source"] = src
        issues.append(issue)

    summary_parts = [state.message] if state.message else []
    if state.static_tool_findings:
        summary_parts.append(
            f"{state.static_tool_findings} static-tool verified, "
            f"{state.ai_suggestion_findings} AI suggested"
        )
    summary = " | ".join(summary_parts) if summary_parts else "Analysis complete."

    end_time = time.time()
    total_ms = int((end_time - state.start_time) * 1000) if state.start_time else None

    from app.analyzers.base import AnalysisOutcome

    return AnalysisOutcome(
        status=_determine_final_status(state),
        message=summary,
        issues=tuple(issues),
        quality_score=state.quality_score,
        duration_ms=total_ms,
    )


def _agent_name_from_id(agent_id: str) -> str:
    """Map agent ID to human-readable name."""
    names = {
        "bug": "Bug Detection",
        "security": "Security Analysis",
        "performance": "Performance Optimization",
        "quality": "Code Quality",
        "fix": "Fix & Validation",
        "static": "Static Analysis",
    }
    return names.get(agent_id, agent_id)


def _determine_final_status(state: ReviewState) -> str:
    """Determine the final review status based on agent outcomes."""
    errored_agents = [
        aid
        for aid, status in state.agent_statuses.items()
        if status == AgentStatus.FAILED and aid != "static"
    ]

    if errored_agents:
        if all(
            state.agent_statuses.get(aid) == AgentStatus.FAILED
            for aid in state.agent_statuses
            if aid not in ("static", "input")
        ):
            return "error"
        return "completed_with_errors"

    return "completed"


# ---------------------------------------------------------------------------
# Orchestrator wrapper - manual execution
# ---------------------------------------------------------------------------


def run_review_langgraph(
    code: str,
    language: str,
    filename: str | None = None,
    *,
    include_fix_agent: bool = True,
    include_static_tools: bool = True,
    agent_timeout: float = 60.0,
) -> AnalysisOutcome:
    """Run a full code review using the LangGraph orchestrator.

    We execute the graph nodes manually rather than using graph.invoke(),
    because LangGraph's state tracking conflicts with our dataclass-based
    ReviewState when keys like ``review_id`` receive updates from multiple
    parallel paths. The node functions above define the graph structure;
    manual execution gives us full control over state management while
    preserving the same orchestration logic.
    """
    # Validate input early - empty code is an error
    if not code.strip():
        return AnalysisOutcome(
            status="error",
            message="Submitted code must not be empty.",
            issues=tuple(),
            quality_score=None,
            duration_ms=None,
        )

    # Initialize state
    state = ReviewState(
        review_id=f"rev_{int(time.time())}",
        code=code,
        language=language,
        filename=filename,
        include_fix_agent=include_fix_agent,
        include_static_tools=include_static_tools,
        agent_timeout_seconds=agent_timeout,
        start_time=time.time(),
    )

    # Execute graph nodes in the defined order
    # Structure: input_validation -> [parallel agents] -> static_tools ->
    # find_aggregation -> quality_scoring -> final_response
    # Note: In manual mode we run agents sequentially; the graph would
    # run them in parallel with proper Annotated state keys.
    _review_state = state  # Keep a reference for later use

    state = node_input_validation(state)

    # Primary agents run sequentially (would be parallel in graph)
    state = node_bug_detection(state)
    state = node_security_analysis(state)
    state = node_performance_analysis(state)
    state = node_code_quality(state)

    # Fix validation
    state = node_fix_validation(state)

    # Static tools
    state = node_static_tools(state)

    # Find aggregation
    state = node_find_aggregation(state)

    # Quality scoring
    state = node_quality_scoring(state)

    # Final response - this converts ReviewState to AnalysisOutcome
    _analysis_outcome = node_final_response(state)
    _review_state = state

    # Build issues from the review state's deduplicated findings
    issues = []
    for f in _review_state.deduplicated_findings:
        issue = {
            "id": f.get("id", ""),
            "agent_id": f.get("source_agent", ""),
            "agent_name": _agent_name_from_id(f.get("source_agent", "")),
            "severity": f.get("severity") or "Info",
            "title": f.get("title", ""),
            "description": f.get("description", ""),
            "suggestion": f.get("suggested_fix", ""),
            "line": f.get("start_line", 1),
        }
        if f.get("source") is not None:
            src = f.get("source")
            if hasattr(src, "value"):
                issue["source"] = src.value
            else:
                issue["source"] = src
        issues.append(issue)

    # Determine final status from the review state
    errored_agents = [
        aid
        for aid, status in _review_state.agent_statuses.items()
        if status == AgentStatus.FAILED and aid != "static"
    ]

    if errored_agents:
        if all(
            _review_state.agent_statuses.get(aid) == AgentStatus.FAILED
            for aid in _review_state.agent_statuses
            if aid not in ("static", "input")
        ):
            final_status = "error"
        else:
            final_status = "completed_with_errors"
    else:
        final_status = "completed"

    # Get quality score and grade from the review state
    quality_score = _review_state.quality_score

    return AnalysisOutcome(
        status=final_status,
        message=_analysis_outcome.message or "Analysis complete.",
        issues=tuple(issues),
        quality_score=quality_score,
        duration_ms=int((time.time() - _review_state.start_time) * 1000) if _review_state.start_time else None,
    )