"""Agent package — Phase 4.

Five specialized code review agents, a static-analysis runner, a
cross-agent deduplicator, and an orchestrator that ties them together.

Individual agent ``analyze()`` functions
-----------------------------------------
Each agent accepts ``(code, language, filename=None)`` and returns a dict
``{"summary": str, "findings": list[dict], "warnings": list[str]}``.

The Fix & Validation Agent additionally accepts a keyword argument
``findings_from_other_agents``.

Orchestrator
------------
``run_all_agents(code, language, filename=None)`` runs all five agents in
parallel (with per-agent timeout) and returns an :class:`~app.agents.orchestrator.OrchestratorResult`.

Static tools
------------
``run_static_analysis(code, language, filename=None)`` runs the deterministic
tools (Ruff, Bandit, ESLint, cppcheck) applicable to the given language.

Deduplication
-------------
``deduplicate_findings(findings)`` merges near-duplicate findings from
different agents into a single authoritative finding.
"""

from __future__ import annotations

from app.agents.bug_agent import analyze as bug_analysis
from app.agents.security_agent import analyze as security_analysis
from app.agents.performance_agent import analyze as performance_analysis
from app.agents.quality_agent import analyze as quality_analysis
from app.agents.fix_agent import analyze as fix_analysis
from app.agents.orchestrator import run_all_agents, OrchestratorResult, AgentResult
from app.agents.static_tools import run_static_analysis
from app.agents.deduplication import deduplicate_findings

__all__ = [
    # Individual agent entry points
    "bug_analysis",
    "security_analysis",
    "performance_analysis",
    "quality_analysis",
    "fix_analysis",
    # Orchestration
    "run_all_agents",
    "OrchestratorResult",
    "AgentResult",
    # Static analysis tools
    "run_static_analysis",
    # Deduplication
    "deduplicate_findings",
]
