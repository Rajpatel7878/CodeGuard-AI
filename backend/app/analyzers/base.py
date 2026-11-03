"""Analysis result types shared by the analyzer pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnalysisOutcome:
    """Outcome of an analysis attempt.

    ``issues`` must stay empty until a real analyzer produces findings. The
    backend never fabricates results.
    """

    status: str
    message: str
    issues: tuple[dict[str, object], ...] = field(default_factory=tuple)
    quality_score: int | None = None
    duration_ms: int | None = None
    agents: tuple[dict[str, object], ...] = field(default_factory=tuple)
