"""LLM provider boundary.

This module reports the configuration honestly so the API can return a pending
status instead of inventing findings. The review pipeline uses Gemini through
:mod:`app.llm.gemini_service`; ``is_available`` is what gates analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings

NOT_CONFIGURED_MESSAGE = (
    "AI analysis is not configured. Set GEMINI_API_KEY in the backend "
    "environment to enable the five review agents; reviews are stored as "
    "pending until then."
)


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

    The only implemented provider is Gemini, configured with ``GEMINI_API_KEY``.
    Legacy ``LLM_PROVIDER`` / ``LLM_API_KEY`` settings are still reported so old
    deployments get an accurate message rather than a silent no-op.
    """
    if settings.gemini_api_key:
        return LlmClient(
            provider="gemini",
            configured=True,
            status="configured",
            message=f"Gemini analysis is enabled ({settings.gemini_model}).",
        )

    provider = (settings.llm_provider or "none").lower()
    if provider != "none" and settings.llm_api_key:
        return LlmClient(
            provider=provider,
            configured=False,
            status="not_configured",
            message=(
                f"LLM provider '{provider}' is selected, but only Gemini is "
                "implemented. Set GEMINI_API_KEY instead; reviews remain pending."
            ),
        )

    return LlmClient(
        provider=provider,
        configured=False,
        status="not_configured",
        message=NOT_CONFIGURED_MESSAGE,
    )
