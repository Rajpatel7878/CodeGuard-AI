"""LLM package.

Phase 2's provider boundary reports whether AI analysis is configured. Phase 3
adds the Gemini review service, which validates every model response before
returning it.
"""

from app.llm.client import NOT_CONFIGURED_MESSAGE, LlmClient, get_llm_client
from app.llm.gemini_service import (
    DEFAULT_MODEL,
    GeminiCodeReviewService,
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    GeminiRequestRejectedError,
    GeminiResponseError,
    GeminiServiceError,
    GeminiTimeoutError,
    get_gemini_service,
    reset_gemini_service,
)
from app.llm.schemas import Finding, FindingSource, GeminiAnalysis, Severity

__all__ = [
    "DEFAULT_MODEL",
    "Finding",
    "FindingSource",
    "GeminiAnalysis",
    "GeminiCodeReviewService",
    "GeminiNotConfiguredError",
    "GeminiRateLimitError",
    "GeminiRequestRejectedError",
    "GeminiResponseError",
    "GeminiServiceError",
    "GeminiTimeoutError",
    "LlmClient",
    "NOT_CONFIGURED_MESSAGE",
    "Severity",
    "get_gemini_service",
    "get_llm_client",
    "reset_gemini_service",
]
