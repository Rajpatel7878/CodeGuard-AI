"""Shared typed state for the LangGraph-based code review orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END


class AgentStatus(str, Enum):
    """Status of an individual agent during review."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """Result produced by one specialized agent."""

    agent_id: str
    agent_name: str
    status: AgentStatus
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    duration_ms: Optional[int] = None


@dataclass
class ReviewState:
    """Shared typed state for the LangGraph review orchestration.

    Uses langgraph's add_messages pattern for fields that may receive
    updates from multiple parallel paths.
    """

    # Core review identity
    review_id: str
    code: str
    language: str
    filename: Optional[str] = None

    # Agent statuses
    agent_statuses: Dict[str, AgentStatus] = field(default_factory=dict)

    # Agent results
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)

    # Agent errors
    agent_errors: Dict[str, str] = field(default_factory=dict)

    # Deduplicated findings
    deduplicated_findings: list[dict[str, Any]] = field(default_factory=list)

    # Quality score and grade
    quality_score: Optional[int] = None
    grade: Optional[str] = None

    # Static tool findings count
    static_tool_findings: int = 0
    ai_suggestion_findings: int = 0

    # Metadata
    include_fix_agent: bool = True
    include_static_tools: bool = True
    agent_timeout_seconds: float = 60.0

    # Raw code analysis metadata
    message: str = ""
    start_time: Optional[float] = None
    total_duration_ms: Optional[int] = None

    # All raw findings before deduplication
    all_findings: list[dict[str, Any]] = field(default_factory=list)


def _init_review_state(code: str, language: str, filename: Optional[str] = None) -> ReviewState:
    """Initialize a ReviewState for a new review."""
    return ReviewState(
        review_id=f"rev_{int(time.time())}",
        code=code,
        language=language,
        filename=filename,
        start_time=time.time(),
    )