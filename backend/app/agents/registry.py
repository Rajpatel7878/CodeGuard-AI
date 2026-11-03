"""The five review agents and their reported statuses."""

from __future__ import annotations

from typing import Final

AGENTS: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "bug",
        "name": "Bug Detection Agent",
        "description": "Traces logic errors, edge cases, and unhandled runtime exceptions.",
    },
    {
        "id": "security",
        "name": "Security Analysis Agent",
        "description": "Checks injection paths, leaked secrets, and missing authorization.",
    },
    {
        "id": "performance",
        "name": "Performance Optimization Agent",
        "description": "Finds hot-path allocations, redundant I/O, and unbounded growth.",
    },
    {
        "id": "quality",
        "name": "Code Quality Agent",
        "description": "Reviews readability, duplication, naming, and module structure.",
    },
    {
        "id": "fix",
        "name": "Fix & Validation Agent",
        "description": "Drafts a fix for each reported issue and validates the patch.",
    },
)


def build_agent_results(status: str) -> list[dict[str, object]]:
    """Return each agent with the given run status and no fabricated findings."""
    return [
        {
            "id": agent["id"],
            "name": agent["name"],
            "status": status,
            "findings": 0,
            "duration_ms": None,
        }
        for agent in AGENTS
    ]
