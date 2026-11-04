"""Multi-agent orchestration for code review.

This module runs all five specialized review agents against a code submission,
collects and deduplicates their findings, and returns a unified result. Each
agent runs in its own thread so a slow or failing agent does not block the
others.

Design principles
-----------------
* **Failure isolation** — an exception raised by one agent is caught, logged,
  and turned into an ``AgentResult`` with ``status="error"``. The overall
  review continues.
* **Timeouts** — each agent is given a configurable wall-clock timeout
  (default 60 s). An agent that exceeds this budget is cancelled; its findings
  are treated as empty.
* **No fabrication** — static tool findings are only added when the tool is
  installed and produced real output. The ``FindingSource`` enum communicates
  provenance to the caller.
* **Deduplication** — findings that describe the same problem at the same
  location are merged (see :mod:`app.agents.deduplication`).
* **Structured output** — every finding carries ``source`` (tool vs AI),
  ``confidence``, and ``source_agent`` (which agent found it).
* **Quota efficiency** — ``review_mode="combined"`` (the default) asks Gemini
  once for all four categories and splits the answer into four agent results,
  instead of four independent requests. ``review_mode="per_agent"`` keeps the
  original behaviour.
* **Quota-aware degradation** — after an HTTP 429 from the active provider
  (OpenRouter or Gemini) the four AI agents are reported as failed with a
  quota message, static findings are kept, and the Fix agent is skipped rather
  than spending a request against an exhausted quota.

Exported API
------------
``run_all_agents(code, language, filename)`` → ``OrchestratorResult``
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agents.deduplication import deduplicate_findings
from app.agents.static_tools import run_static_analysis
from app.config import settings
from app.llm.gemini_service import GeminiRateLimitError, GeminiServiceError

logger = logging.getLogger(__name__)

# Default per-agent timeout in seconds. It is derived from the largest provider
# retry budget so an agent is never abandoned while its retries are still valid.
import os
_PROVIDER_RETRY_BUDGET = max(
    settings.gemini_timeout_seconds * settings.gemini_max_attempts,
    settings.openrouter_timeout_seconds * settings.openrouter_max_attempts,
)
_AGENT_TIMEOUT: float = float(
    os.getenv(
        "AGENT_TIMEOUT_SECONDS",
        str(max(60.0, _PROVIDER_RETRY_BUDGET + 10)),
    )
)

# "combined" uses one Gemini request for all four categories; "per_agent"
# gives each agent its own request (four times the quota).
_DEFAULT_REVIEW_MODE: str = (settings.gemini_review_mode or "combined").strip().lower()
_REVIEW_MODES: tuple[str, ...] = ("combined", "per_agent")


@dataclass
class AgentResult:
    """Result produced by one specialized agent."""

    agent_id: str
    agent_name: str
    status: str            # "ok" | "error" | "timeout" | "skipped"
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int | None = None
    error_message: str | None = None


@dataclass
class OrchestratorResult:
    """Aggregated result from all agents for one code submission."""

    status: str            # "ok" | "partial" | "error"
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)
    total_duration_ms: int | None = None
    static_tool_findings: int = 0
    ai_suggestion_findings: int = 0


# ---------------------------------------------------------------------------
# Individual agent runners (import lazily to avoid circular imports)
# ---------------------------------------------------------------------------

def _run_bug_agent(
    code: str, language: str, filename: str | None
) -> dict[str, Any]:
    from app.agents.bug_agent import analyze
    return analyze(code, language, filename=filename)


def _run_security_agent(
    code: str, language: str, filename: str | None
) -> dict[str, Any]:
    from app.agents.security_agent import analyze
    return analyze(code, language, filename=filename)


def _run_performance_agent(
    code: str, language: str, filename: str | None
) -> dict[str, Any]:
    from app.agents.performance_agent import analyze
    return analyze(code, language, filename=filename)


def _run_quality_agent(
    code: str, language: str, filename: str | None
) -> dict[str, Any]:
    from app.agents.quality_agent import analyze
    return analyze(code, language, filename=filename)


# One combined Gemini request for all four categories (quota-efficient mode).
def _run_combined_agent(
    code: str, language: str, filename: str | None
) -> dict[str, Any]:
    from app.agents.combined_agent import analyze as analyze_combined
    return analyze_combined(code, language, filename=filename)


# Fix agent is run after the other four; it receives their consolidated findings
def _run_fix_agent(
    code: str,
    language: str,
    filename: str | None,
    findings_from_other_agents: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.agents.fix_agent import analyze
    return analyze(
        code,
        language,
        filename=filename,
        findings_from_other_agents=findings_from_other_agents,
    )


# ---------------------------------------------------------------------------
# Agent descriptors
# ---------------------------------------------------------------------------

_PRIMARY_AGENTS: tuple[tuple[str, str, Callable], ...] = (
    ("bug", "Bug Detection Agent", _run_bug_agent),
    ("security", "Security Analysis Agent", _run_security_agent),
    ("performance", "Performance Optimization Agent", _run_performance_agent),
    ("quality", "Code Quality Agent", _run_quality_agent),
)


def _get_primary_agents():
    # Allow tests to patch module-level functions
    return (
        ("bug", "Bug Detection Agent", globals().get("_run_bug_agent", _run_bug_agent)),
        ("security", "Security Analysis Agent", globals().get("_run_security_agent", _run_security_agent)),
        ("performance", "Performance Optimization Agent", globals().get("_run_performance_agent", _run_performance_agent)),
        ("quality", "Code Quality Agent", globals().get("_run_quality_agent", _run_quality_agent)),
    )


# ---------------------------------------------------------------------------
# Primary agent execution (per-agent and combined modes)
# ---------------------------------------------------------------------------

def _run_primary_agents_parallel(
    code: str,
    language: str,
    filename: str | None,
    agent_timeout: float,
    primary_agents: tuple[tuple[str, str, Callable], ...],
) -> tuple[list[AgentResult], list[dict[str, Any]]]:
    """Run each primary agent as its own request (four Gemini calls)."""
    results: list[AgentResult] = []
    findings: list[dict[str, Any]] = []

    pool = ThreadPoolExecutor(max_workers=len(primary_agents))
    try:
        future_to_agent = {
            pool.submit(
                _execute_agent,
                agent_id,
                agent_name,
                fn,
                (code, language, filename),
            ): (agent_id, agent_name)
            for agent_id, agent_name, fn in primary_agents
        }

        collected: set[Any] = set()
        try:
            for future in as_completed(future_to_agent, timeout=agent_timeout + 5):
                collected.add(future)
                agent_id, agent_name = future_to_agent[future]
                try:
                    result: AgentResult = future.result(timeout=agent_timeout)
                    results.append(result)
                    if result.status == "ok":
                        findings.extend(result.findings)
                except FutureTimeoutError:
                    logger.warning("Agent '%s' timed out after %ss", agent_id, agent_timeout)
                    results.append(
                        AgentResult(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            status="timeout",
                            error_message=f"Agent timed out after {agent_timeout}s.",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected error collecting result for agent '%s'", agent_id)
                    results.append(
                        AgentResult(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            status="error",
                            error_message=f"{type(exc).__name__}: {exc}",
                        )
                    )
        except FutureTimeoutError:
            # The overall wait expired: record every unfinished agent as a
            # timeout so the review reports partial failure instead of raising.
            logger.warning("Agent collection timed out after %ss", agent_timeout + 5)
            for future, (agent_id, agent_name) in future_to_agent.items():
                if future in collected:
                    continue
                future.cancel()
                results.append(
                    AgentResult(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        status="timeout",
                        error_message=f"Agent timed out after {agent_timeout}s.",
                    )
                )
    finally:
        # Do not block the request on threads that already exceeded their
        # budget; their results are recorded as timeouts above.
        pool.shutdown(wait=False, cancel_futures=True)

    return results, findings


def _run_primary_agents_combined(
    code: str,
    language: str,
    filename: str | None,
    agent_timeout: float,
    primary_agents: tuple[tuple[str, str, Callable], ...],
) -> tuple[list[AgentResult], list[dict[str, Any]], bool]:
    """Ask Gemini once, then split the answer into four agent results.

    Returns ``(agent_results, findings, quota_exceeded)``. On any failure all
    four agents are reported as failed with the provider's message; no finding
    is invented to fill the gap, and static findings are unaffected.
    """
    start = time.monotonic()
    combined_fn = globals().get("_run_combined_agent", _run_combined_agent)
    failure_status = "error"
    failure_message: str | None = None
    quota_exceeded = False
    raw: Any = None

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(combined_fn, code, language, filename)
            raw = future.result(timeout=agent_timeout)
    except FutureTimeoutError:
        failure_status = "timeout"
        failure_message = f"Combined analysis timed out after {agent_timeout}s."
    except GeminiRateLimitError as exc:
        quota_exceeded = True
        failure_message = str(exc)
    except GeminiServiceError as exc:
        failure_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Combined review raised an unexpected error")
        failure_message = f"{type(exc).__name__}: {exc}"

    duration_ms = int((time.monotonic() - start) * 1000)

    if not isinstance(raw, dict):
        logger.warning("Combined review failed: %s", failure_message)
        return (
            [
                AgentResult(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    status=failure_status,
                    duration_ms=duration_ms,
                    error_message=failure_message,
                )
                for agent_id, agent_name, _ in primary_agents
            ],
            [],
            quota_exceeded,
        )

    categories = raw.get("categories") or {}
    results: list[AgentResult] = []
    findings: list[dict[str, Any]] = []
    for agent_id, agent_name, _ in primary_agents:
        section = categories.get(agent_id) or {}
        section_findings = [dict(f) for f in (section.get("findings") or [])]
        for finding in section_findings:
            finding.setdefault("source_agent", agent_id)
        results.append(
            AgentResult(
                agent_id=agent_id,
                agent_name=agent_name,
                status="ok",
                summary=section.get("summary") or raw.get("summary") or "",
                findings=section_findings,
                duration_ms=duration_ms,
            )
        )
        findings.extend(section_findings)

    return results, findings, quota_exceeded


def _format_failure_details(agent_results: list[AgentResult]) -> list[str]:
    """Describe failures once per distinct message.

    Combined mode fails all four categories with the same provider message;
    stating it four times would bury the reason in repetition.
    """
    grouped: dict[str, list[str]] = {}
    for result in agent_results:
        if result.status in ("error", "timeout") and result.error_message:
            grouped.setdefault(result.error_message, []).append(result.agent_name)

    details: list[str] = []
    for message, names in grouped.items():
        if len(names) == 1:
            details.append(f"{names[0]}: {message}")
        else:
            details.append(f"{len(names)} agents reported: {message}")
    return details


# ---------------------------------------------------------------------------
# Orchestration logic
# ---------------------------------------------------------------------------

def _execute_agent(
    agent_id: str,
    agent_name: str,
    fn: Callable,
    args: tuple,
) -> AgentResult:
    """Run one agent function and wrap the result in an ``AgentResult``.

    Never raises — all exceptions are caught and recorded.
    """
    start = time.monotonic()
    try:
        raw: dict[str, Any] = fn(*args)
        duration_ms = int((time.monotonic() - start) * 1000)
        findings = list(raw.get("findings") or [])
        # Tag each finding with the originating agent
        for f in findings:
            f.setdefault("source_agent", agent_id)
        return AgentResult(
            agent_id=agent_id,
            agent_name=agent_name,
            status="ok",
            summary=raw.get("summary") or "",
            findings=findings,
            duration_ms=duration_ms,
        )
    except GeminiServiceError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Agent '%s' raised GeminiServiceError: %s", agent_id, exc)
        return AgentResult(
            agent_id=agent_id,
            agent_name=agent_name,
            status="error",
            duration_ms=duration_ms,
            error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Agent '%s' raised unexpected error", agent_id)
        return AgentResult(
            agent_id=agent_id,
            agent_name=agent_name,
            status="error",
            duration_ms=duration_ms,
            error_message=f"{type(exc).__name__}: {exc}",
        )


def run_all_agents(
    code: str,
    language: str,
    filename: str | None = None,
    *,
    agent_timeout: float = _AGENT_TIMEOUT,
    include_fix_agent: bool = True,
    include_static_tools: bool = True,
    review_mode: str | None = None,
) -> OrchestratorResult:
    """Run all code-review agents and return deduplicated findings.

    Parameters
    ----------
    code:
        The source code to review. Treated as untrusted data; never executed.
    language:
        Language identifier (e.g. ``"python"``, ``"javascript"``).
    filename:
        Optional file name used for display and to pick the right file extension
        when writing temporary files for static tools.
    agent_timeout:
        Per-agent wall-clock timeout in seconds. Agents that exceed this are
        cancelled and their contribution is recorded as ``status="timeout"``.
    include_fix_agent:
        Set False to skip the Fix & Validation Agent (useful in tests).
    include_static_tools:
        Set False to skip all static analysis tools (useful in tests).
    review_mode:
        ``"combined"`` (default) sends one Gemini request for all four
        categories; ``"per_agent"`` runs four independent requests. Unknown
        values fall back to the configured default.

    Returns
    -------
    OrchestratorResult
        A single aggregated result; individual agent outcomes are available in
        ``agent_results`` for dashboards.
    """
    overall_start = time.monotonic()
    agent_results: list[AgentResult] = []

    # ------------------------------------------------------------------
    # Step 1: Static analysis tools (synchronous, fast)
    # ------------------------------------------------------------------
    static_findings: list[dict[str, Any]] = []
    if include_static_tools:
        try:
            static_fn = globals().get("run_static_analysis", run_static_analysis)
            static_findings = static_fn(code, language, filename)
            for f in static_findings:
                f.setdefault("source_agent", "static")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Static analysis raised an unexpected error: %s", exc)

    # ------------------------------------------------------------------
    # Step 2: Primary AI agents
    # ------------------------------------------------------------------
    primary_ai_findings: list[dict[str, Any]] = []
    quota_exceeded = False

    primary_agents = _get_primary_agents()
    mode = (review_mode or _DEFAULT_REVIEW_MODE or "combined").strip().lower()
    if mode not in _REVIEW_MODES:
        logger.warning("Unknown review mode %r; using 'combined'.", mode)
        mode = "combined"

    if mode == "combined":
        combined_results, primary_ai_findings, quota_exceeded = (
            _run_primary_agents_combined(
                code, language, filename, agent_timeout, primary_agents
            )
        )
        agent_results.extend(combined_results)
    else:
        parallel_results, primary_ai_findings = _run_primary_agents_parallel(
            code, language, filename, agent_timeout, primary_agents
        )
        agent_results.extend(parallel_results)

    # Restore canonical agent order for the dashboard
    order = {aid: i for i, (aid, _, _) in enumerate(primary_agents)}
    agent_results.sort(key=lambda r: order.get(r.agent_id, 99))

    # ------------------------------------------------------------------
    # Step 3: Deduplicate primary findings (AI + static combined)
    # ------------------------------------------------------------------
    all_primary = list(static_findings) + primary_ai_findings
    deduped_findings = deduplicate_findings(all_primary)

    # ------------------------------------------------------------------
    # Step 4: Fix & Validation Agent (sequential, needs prior findings)
    # ------------------------------------------------------------------
    fix_result: AgentResult | None = None
    fix_findings: list[dict[str, Any]] = []

    if include_fix_agent and deduped_findings and quota_exceeded:
        # No fix request against an exhausted quota: it would fail too and
        # only consume more of the allowance. The workflow is unchanged for
        # every other review.
        fix_result = AgentResult(
            agent_id="fix",
            agent_name="Fix & Validation Agent",
            status="skipped",
            summary=(
                "Skipped: the AI provider's quota is exhausted, so no fix "
                "request was made."
            ),
        )
    elif include_fix_agent and deduped_findings:
        fix_start = time.monotonic()
        try:
            fix_agent_fn = globals().get("_run_fix_agent", _run_fix_agent)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    _execute_agent,
                    "fix",
                    "Fix & Validation Agent",
                    fix_agent_fn,
                    (code, language, filename, deduped_findings),
                )
                try:
                    fix_result = future.result(timeout=agent_timeout)
                    if fix_result.status == "ok":
                        fix_findings = fix_result.findings
                        for f in fix_findings:
                            f.setdefault("source_agent", "fix")
                except FutureTimeoutError:
                    logger.warning("Fix agent timed out after %ss", agent_timeout)
                    fix_result = AgentResult(
                        agent_id="fix",
                        agent_name="Fix & Validation Agent",
                        status="timeout",
                        error_message=f"Fix agent timed out after {agent_timeout}s.",
                    )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fix agent raised an unexpected error")
            fix_result = AgentResult(
                agent_id="fix",
                agent_name="Fix & Validation Agent",
                status="error",
                error_message=f"{type(exc).__name__}: {exc}",
            )
    elif include_fix_agent:
        fix_result = AgentResult(
            agent_id="fix",
            agent_name="Fix & Validation Agent",
            status="skipped",
            summary="No findings from other agents to fix.",
        )

    if fix_result:
        agent_results.append(fix_result)

    # ------------------------------------------------------------------
    # Step 5: Assemble final result
    # ------------------------------------------------------------------
    all_findings = deduped_findings + fix_findings
    total_duration_ms = int((time.monotonic() - overall_start) * 1000)

    # Count findings by source
    from app.llm.schemas import FindingSource as FS
    static_count = sum(
        1
        for f in all_findings
        if (
            f.get("source") == FS.STATIC_ANALYSIS
            or f.get("source") == FS.STATIC_ANALYSIS.value
        )
    )
    ai_count = len(all_findings) - static_count

    # Determine overall status. Agents that never had work to do (the fix
    # agent with no findings) are skipped, not successes: counting them would
    # turn a total agent failure into a cheerful "partial" result.
    errored = [r for r in agent_results if r.status in ("error", "timeout")]
    attempted = [r for r in agent_results if r.status != "skipped"]
    if errored and len(errored) == len(attempted):
        overall_status = "error"
    elif errored:
        overall_status = "partial"
    else:
        overall_status = "ok"

    # Build a combined summary. Failures are stated explicitly so an
    # errored review can never read like a clean one.
    # Combined mode reports one shared summary per category; deduplicate so it
    # is stated once instead of four times.
    ok_summaries = list(
        dict.fromkeys(
            r.summary for r in agent_results if r.status == "ok" and r.summary
        )
    )
    if ok_summaries:
        combined_summary = "; ".join(ok_summaries)
    elif overall_status == "error":
        combined_summary = "No review agent completed successfully."
    else:
        combined_summary = "No findings were reported."

    failure_details = _format_failure_details(agent_results)
    if failure_details:
        combined_summary += " Failed: " + "; ".join(failure_details)

    return OrchestratorResult(
        status=overall_status,
        summary=combined_summary,
        findings=all_findings,
        agent_results=agent_results,
        total_duration_ms=total_duration_ms,
        static_tool_findings=static_count,
        ai_suggestion_findings=ai_count,
    )
