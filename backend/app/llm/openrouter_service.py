"""OpenRouter-backed source code review.

OpenRouter is a second provider alongside Gemini. It uses the same prompt
building, JSON parsing, and finding trust boundary as
:class:`~app.llm.gemini_service.GeminiCodeReviewService`; only the transport and
the provider-specific labels are replaced here.

The default model is ``openrouter/free``, OpenRouter's Free Models Router. It
picks a free model per request and reports which one it used in the response's
``model`` field, which is logged for debugging (the key itself never is).

Configuration comes from the backend environment:

* ``OPENROUTER_API_KEY`` - required; never logged, never returned by the API.
* ``OPENROUTER_BASE_URL`` - default ``https://openrouter.ai/api/v1``.
* ``OPENROUTER_MODEL`` - default ``openrouter/free``.
* ``OPENROUTER_TIMEOUT_SECONDS`` - per-attempt timeout, default 45s.
* ``OPENROUTER_MAX_ATTEMPTS`` - total attempts including the first, default 3.
* ``OPENROUTER_QUOTA_COOLDOWN_SECONDS`` - pause after HTTP 429, default 300s.
* ``OPENROUTER_HTTP_REFERER`` / ``OPENROUTER_APP_TITLE`` - attribution headers.

An HTTP 429 is never retried: it means the free-tier limit is exhausted, so the
service records a process-wide cooldown and later calls fail fast with a clear
message instead of spending more allowance.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.config import settings
from app.llm.gemini_service import (
    RATE_LIMIT_STATUS_CODE,
    RETRYABLE_STATUS_CODES,
    GeminiCodeReviewService,
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    GeminiRequestRejectedError,
    GeminiResponseError,
    GeminiServiceError,
    GeminiTimeoutError,
    _QuotaGate,
    quota_exceeded_message,
)

logger = logging.getLogger(__name__)

#: Free Models Router: OpenRouter selects a free model per request.
DEFAULT_MODEL = "openrouter/free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_HTTP_REFERER = "https://code-guard-ai-rho.vercel.app"
DEFAULT_APP_TITLE = "ALPHA CodeGuard AI"

#: Chat-completions path appended to ``OPENROUTER_BASE_URL``.
CHAT_COMPLETIONS_PATH = "/chat/completions"

#: Finish reasons that mean the model did not return a usable review.
INCOMPLETE_FINISH_REASONS = frozenset({"length"})
BLOCKED_FINISH_REASONS = frozenset({"content_filter"})

NOT_CONFIGURED_MESSAGE = (
    "OpenRouter analysis is not configured. Set OPENROUTER_API_KEY in the "
    "backend environment to enable AI findings."
)


class OpenRouterServiceError(GeminiServiceError):
    """Base class for transport-level OpenRouter failures."""


class OpenRouterNotConfiguredError(GeminiNotConfiguredError):
    """Raised when no OpenRouter API key is configured."""


class OpenRouterTimeoutError(GeminiTimeoutError):
    """Raised when every attempt timed out."""

    retryable = True


class OpenRouterRateLimitError(GeminiRateLimitError):
    """Raised when OpenRouter reports an exhausted free-tier rate limit."""

    retryable = False


class OpenRouterRequestRejectedError(GeminiRequestRejectedError):
    """Raised for non-retryable client errors such as a bad key or model id."""


class OpenRouterResponseError(GeminiResponseError):
    """Raised when the model response is blocked, empty, or unparseable."""


_quota_gate = _QuotaGate()


@dataclass(frozen=True)
class _Completion:
    """The text content of one OpenRouter chat completion."""

    text: str


def _coerce_content(content: Any) -> str:
    """Read message content whether it is a string or a list of text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


class OpenRouterCodeReviewService(GeminiCodeReviewService):
    """Runs one OpenRouter review request and returns validated findings.

    ``analyze`` and ``analyze_combined`` - including the four-category
    combined prompt - are inherited from the Gemini service. This class only
    replaces the HTTP transport, the error mapping, and the provider labels.
    The HTTP client is created lazily on first use and reused.
    """

    display_name = "OpenRouter"
    api_key_env_var = "OPENROUTER_API_KEY"
    model_env_var = "OPENROUTER_MODEL"
    not_configured_message = NOT_CONFIGURED_MESSAGE
    not_configured_error = OpenRouterNotConfiguredError
    service_error = OpenRouterServiceError
    request_rejected_error = OpenRouterRequestRejectedError
    response_error = OpenRouterResponseError
    rate_limit_error = OpenRouterRateLimitError
    timeout_error = OpenRouterTimeoutError
    quota_gate = _quota_gate

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        quota_cooldown_seconds: float = 300.0,
        http_referer: str = DEFAULT_HTTP_REFERER,
        app_title: str = DEFAULT_APP_TITLE,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            quota_cooldown_seconds=quota_cooldown_seconds,
            client=client,
            sleep=sleep,
            random_value=random_value,
        )
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.http_referer = (
            http_referer or DEFAULT_HTTP_REFERER
        ).strip() or DEFAULT_HTTP_REFERER
        self.app_title = (app_title or DEFAULT_APP_TITLE).strip() or DEFAULT_APP_TITLE

    def __repr__(self) -> str:
        # Never include the key, even if the object is logged by accident.
        return (
            f"OpenRouterCodeReviewService(model={self.model!r}, "
            f"base_url={self.base_url!r}, configured={self.is_configured}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )

    @classmethod
    def from_settings(cls, **overrides: Any) -> "OpenRouterCodeReviewService":
        """Build a service from the backend environment configuration."""
        return cls(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            timeout_seconds=settings.openrouter_timeout_seconds,
            max_attempts=settings.openrouter_max_attempts,
            quota_cooldown_seconds=settings.openrouter_quota_cooldown_seconds,
            http_referer=settings.openrouter_http_referer,
            app_title=settings.openrouter_app_title,
            **overrides,
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _build_client(self) -> Any:
        """Create an HTTP client with a bounded per-request timeout."""
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx is a requirement
            raise OpenRouterNotConfiguredError(
                "The httpx package is not installed. Run "
                "'pip install -r requirements.txt' in backend/."
            ) from exc

        return httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
        )

    def _headers(self) -> dict[str, str]:
        """Request headers. The bearer token never leaves this method unredacted."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-OpenRouter-Title": self.app_title,
        }

    def _request(
        self,
        client: Any,
        prompt: str,
        system_instruction: str | None = None,
    ) -> _Completion:
        """Perform one chat-completions call and read its content."""
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction or "",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            # The Free Models Router filters for models that support this.
            "response_format": {"type": "json_object"},
        }
        try:
            response = client.post(
                f"{self.base_url}{CHAT_COMPLETIONS_PATH}",
                json=payload,
                headers=self._headers(),
            )
        except GeminiServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - every transport failure is translated
            raise self._translate_error(exc) from None

        return self._read_response(response)

    def _read_response(self, response: Any) -> _Completion:
        """Turn an HTTP response into completion text or a clear service error."""
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            raise self._http_error(response, status_code)

        payload = self._json_payload(response)
        if payload.get("error"):
            raise OpenRouterResponseError(
                "OpenRouter returned an error instead of a review: "
                f"{self._error_detail(payload.get('error'))}"
            )

        self._log_returned_model(payload)

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenRouterResponseError(
                "OpenRouter returned no choices, so no findings could be read."
            )

        choice = choices[0]
        if not isinstance(choice, dict):
            raise OpenRouterResponseError(
                "OpenRouter returned a malformed choice, so no findings could be read."
            )

        finish_reason = str(choice.get("finish_reason") or "").strip().lower()
        if finish_reason in BLOCKED_FINISH_REASONS:
            raise OpenRouterResponseError(
                f"OpenRouter blocked the request ({finish_reason}). "
                "No findings were produced."
            )
        if finish_reason in INCOMPLETE_FINISH_REASONS:
            raise OpenRouterResponseError(
                "OpenRouter stopped before returning a complete review "
                f"({finish_reason})."
            )

        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = _coerce_content(content)
        if not text.strip():
            raise OpenRouterResponseError("OpenRouter returned an empty response.")
        return _Completion(text=text)

    def _extract_text(self, response: _Completion) -> str:
        if not isinstance(response, _Completion):
            raise OpenRouterResponseError(
                "OpenRouter returned an unexpected response shape."
            )
        if not response.text.strip():
            raise OpenRouterResponseError("OpenRouter returned an empty response.")
        return response.text

    def _json_payload(self, response: Any) -> dict[str, Any]:
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            raise OpenRouterResponseError(
                "OpenRouter returned a response that was not valid JSON."
            ) from None
        if not isinstance(payload, dict):
            raise OpenRouterResponseError(
                "OpenRouter returned JSON that is not an object, so no findings "
                "could be read."
            )
        return payload

    def _log_returned_model(self, payload: dict[str, Any]) -> None:
        """Log which model the router actually used, for debugging."""
        returned_model = payload.get("model")
        if isinstance(returned_model, str) and returned_model.strip():
            logger.info(
                "OpenRouter completed the request with model '%s' (requested '%s')",
                returned_model.strip(),
                self.model,
            )
            return
        logger.warning(
            "OpenRouter response did not report the model that handled the "
            "request (requested '%s')",
            self.model,
        )

    def _http_error(self, response: Any, status_code: int) -> OpenRouterServiceError:
        """Map an HTTP error status to a provider-specific service error."""
        suffix = self._error_suffix(response)

        if status_code == RATE_LIMIT_STATUS_CODE:
            # Do not retry and pause every OpenRouter call in this process.
            self.quota_gate.block(self.quota_cooldown_seconds)
            return OpenRouterRateLimitError(
                quota_exceeded_message(
                    self.model, provider=self.display_name
                )
                + suffix,
                retryable=False,
            )
        if status_code in (401, 403):
            return OpenRouterRequestRejectedError(
                f"OpenRouter rejected the request (HTTP {status_code}). Check "
                f"that OPENROUTER_API_KEY is valid and has access to "
                f"'{self.model}'.{suffix}"
            )
        if status_code == 404:
            return OpenRouterRequestRejectedError(
                f"OpenRouter model '{self.model}' is not available "
                f"(HTTP 404). Set OPENROUTER_MODEL to a supported model.{suffix}"
            )
        if status_code in (400, 422):
            return OpenRouterRequestRejectedError(
                f"OpenRouter rejected the review request "
                f"(HTTP {status_code}).{suffix}"
            )
        if status_code in RETRYABLE_STATUS_CODES or status_code >= 500:
            return OpenRouterServiceError(
                f"OpenRouter is temporarily unavailable (HTTP {status_code}).{suffix}",
                retryable=True,
            )
        return OpenRouterServiceError(
            f"OpenRouter request failed (HTTP {status_code}).{suffix}"
        )

    def _error_suffix(self, response: Any) -> str:
        """Read OpenRouter's error message and scrub it for safe surfacing."""
        payload: Any = None
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            payload = None

        detail = ""
        if isinstance(payload, dict):
            detail = self._error_detail(payload.get("error"))
        if not detail:
            text = getattr(response, "text", "")
            if isinstance(text, str):
                detail = text
        if not detail:
            return ""
        return f" {self._scrub(detail)}"

    def _error_detail(self, error: Any) -> str:
        """Extract a human-readable message from an OpenRouter error object."""
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return self._scrub(message)
            return self._scrub(json.dumps(error, default=str))
        if isinstance(error, str):
            return self._scrub(error)
        return ""

    def _translate_error(self, exc: BaseException) -> GeminiServiceError:
        """Map a transport failure to a clear OpenRouter service error."""
        try:
            import httpx
        except ImportError:  # pragma: no cover - httpx is a requirement
            httpx = None  # type: ignore[assignment]

        if httpx is not None:
            if isinstance(exc, httpx.TimeoutException):
                return OpenRouterTimeoutError(
                    f"OpenRouter did not respond within "
                    f"{self.timeout_seconds:g} seconds."
                )
            if isinstance(exc, httpx.TransportError):
                return OpenRouterServiceError(
                    "Could not reach the OpenRouter API.", retryable=True
                )
        if isinstance(exc, TimeoutError):
            return OpenRouterTimeoutError(
                f"OpenRouter did not respond within {self.timeout_seconds:g} seconds."
            )
        if isinstance(exc, ConnectionError):
            return OpenRouterServiceError(
                "Could not reach the OpenRouter API.", retryable=True
            )
        return OpenRouterServiceError(
            f"Unexpected OpenRouter client failure ({type(exc).__name__})."
        )


_service: OpenRouterCodeReviewService | None = None


def get_openrouter_service() -> OpenRouterCodeReviewService:
    """Return the process-wide OpenRouter service, built from settings."""
    global _service
    if _service is None:
        _service = OpenRouterCodeReviewService.from_settings()
    return _service


def reset_openrouter_service() -> None:
    """Drop the cached service so the next call re-reads configuration."""
    global _service
    _service = None


def reset_quota_state() -> None:
    """Clear the OpenRouter quota pause. Used by tests and config reloads."""
    _quota_gate.reset()


def quota_cooldown_remaining() -> float:
    """Seconds left on the process-wide OpenRouter quota pause."""
    return _quota_gate.remaining()
