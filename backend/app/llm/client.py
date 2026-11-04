"""LLM provider boundary.

This module reports the configuration honestly so the API can return a pending
status instead of inventing findings. The review pipeline uses the active
provider through :mod:`app.llm.provider`; ``is_available`` is what gates
analysis. OpenRouter (the free-models router) is preferred by default, with
Gemini kept as an alternative.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.llm.provider import (
    GEMINI,
    NO_PROVIDER_MESSAGE,
    OPENROUTER,
    preferred_provider,
    resolve_provider,
)

NOT_CONFIGURED_MESSAGE = NO_PROVIDER_MESSAGE


@dataclass(frozen=True)
class LlmClient:
    provider: str
    configured: bool
    status: str
    message: str

    @property
    def is_available(self) -> bool:
        return self.configured


def get_llm_client() -> LlmClient:
    """Describe the current analysis engine without contacting a provider.

    The active provider is selected by :func:`app.llm.provider.resolve_provider`
    from ``DEFAULT_LLM_PROVIDER`` and the configured API keys.
    """
    provider = resolve_provider()
    if provider == OPENROUTER:
        return LlmClient(
            provider=OPENROUTER,
            configured=True,
            status="configured",
            message=f"OpenRouter analysis is enabled ({settings.openrouter_model}).",
        )
    if provider == GEMINI:
        return LlmClient(
            provider=GEMINI,
            configured=True,
            status="configured",
            message=f"Gemini analysis is enabled ({settings.gemini_model}).",
        )

    return LlmClient(
        provider=preferred_provider(),
        configured=False,
        status="not_configured",
        message=NOT_CONFIGURED_MESSAGE,
    )
