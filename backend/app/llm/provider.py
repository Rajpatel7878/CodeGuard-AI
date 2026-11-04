"""Active LLM provider selection.

The review agents call :func:`get_review_service` instead of a provider-specific
getter. The preferred provider is ``DEFAULT_LLM_PROVIDER`` (``openrouter`` by
default). If that provider has no API key but the other one does, the configured
provider is used so an existing Gemini-only deployment keeps working.

Only one service object per provider is cached, and the key is read from the
backend environment. API keys are never logged or returned by the API.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import settings
from app.llm.gemini_service import GeminiCodeReviewService
from app.llm.openrouter_service import (
    OpenRouterCodeReviewService,
    OpenRouterNotConfiguredError,
)

logger = logging.getLogger(__name__)

OPENROUTER = "openrouter"
GEMINI = "gemini"
SUPPORTED_PROVIDERS: tuple[str, ...] = (OPENROUTER, GEMINI)

NO_PROVIDER_MESSAGE = (
    "AI analysis is not configured. Set OPENROUTER_API_KEY for the default "
    "OpenRouter free-models router, or GEMINI_API_KEY for Gemini, in the "
    "backend environment to enable the five review agents; reviews are stored "
    "as pending until then."
)

_services: dict[str, Any] = {}
_lock = threading.Lock()


def preferred_provider() -> str:
    """Return the configured provider name, defaulting to OpenRouter."""
    name = (settings.default_llm_provider or OPENROUTER).strip().lower()
    return name if name in SUPPORTED_PROVIDERS else OPENROUTER


def provider_is_configured(provider: str) -> bool:
    """Whether a provider has an API key configured. No network call is made."""
    if provider == OPENROUTER:
        return bool(settings.openrouter_api_key)
    if provider == GEMINI:
        return bool(settings.gemini_api_key)
    return False


def resolve_provider() -> str | None:
    """Pick the provider that should run reviews, or ``None`` if none is set up.

    The preferred provider wins when it has a key. Otherwise the other provider
    is used if it is configured, which keeps Gemini-only deployments working
    after OpenRouter became the default.
    """
    preferred = preferred_provider()
    if provider_is_configured(preferred):
        return preferred

    fallback = GEMINI if preferred == OPENROUTER else OPENROUTER
    if provider_is_configured(fallback):
        logger.info(
            "Preferred LLM provider '%s' has no API key; using '%s' instead.",
            preferred,
            fallback,
        )
        return fallback
    return None


def get_review_service() -> GeminiCodeReviewService | OpenRouterCodeReviewService:
    """Return the cached service for the active provider.

    Raises the provider's not-configured error when no API key is available;
    callers must not turn that into a clean review.
    """
    provider = resolve_provider()
    if provider is None:
        preferred = preferred_provider()
        if preferred == OPENROUTER:
            raise OpenRouterNotConfiguredError(NO_PROVIDER_MESSAGE)
        raise GeminiNotConfiguredError(NO_PROVIDER_MESSAGE)

    service = _services.get(provider)
    if service is not None:
        return service

    with _lock:
        service = _services.get(provider)
        if service is None:
            if provider == OPENROUTER:
                service = OpenRouterCodeReviewService.from_settings()
            else:
                service = GeminiCodeReviewService.from_settings()
            _services[provider] = service
    return service


def reset_review_service() -> None:
    """Drop cached services so the next call re-reads configuration."""
    with _lock:
        _services.clear()
