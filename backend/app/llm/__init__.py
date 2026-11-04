"""LLM package.

The provider boundary reports whether AI analysis is configured. Two providers
are implemented: Gemini and OpenRouter (the free-models router). Both validate
every model response before returning it.
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
from app.llm.openrouter_service import (
    OpenRouterCodeReviewService,
    OpenRouterNotConfiguredError,
    OpenRouterRateLimitError,
    OpenRouterRequestRejectedError,
    OpenRouterResponseError,
    OpenRouterServiceError,
    OpenRouterTimeoutError,
    get_openrouter_service,
    reset_openrouter_service,
)
from app.llm.provider import (
    get_review_service,
    preferred_provider,
    reset_review_service,
    resolve_provider,
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
    "OpenRouterCodeReviewService",
    "OpenRouterNotConfiguredError",
    "OpenRouterRateLimitError",
    "OpenRouterRequestRejectedError",
    "OpenRouterResponseError",
    "OpenRouterServiceError",
    "OpenRouterTimeoutError",
    "Severity",
    "get_gemini_service",
    "get_llm_client",
    "get_openrouter_service",
    "get_review_service",
    "preferred_provider",
    "reset_gemini_service",
    "reset_openrouter_service",
    "reset_review_service",
    "resolve_provider",
]
