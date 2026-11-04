"""Gemini-backed source code review.

The submitted code is only ever sent to the model as prompt text. Nothing here
executes, imports, or evaluates it, and model output is parsed into Pydantic
models before it is returned to callers.

Configuration comes from the backend environment:

* ``GEMINI_API_KEY`` - required; never logged, never returned by the API.
* ``GEMINI_MODEL`` - model id, default :data:`DEFAULT_MODEL`.
* ``GEMINI_TIMEOUT_SECONDS`` - per-attempt timeout, default 45s.
* ``GEMINI_MAX_ATTEMPTS`` - total attempts including the first, default 3.
* ``GEMINI_QUOTA_COOLDOWN_SECONDS`` - pause after HTTP 429, default 300s.

Two entry points keep quota use predictable:

* :meth:`GeminiCodeReviewService.analyze` reviews one category (legacy path).
* :meth:`GeminiCodeReviewService.analyze_combined` asks once and fills all
  four agent categories, which uses a quarter of the requests.

An HTTP 429 is never retried: it means the quota is exhausted, so the service
records a process-wide cooldown and later calls fail fast with a clear quota
message instead of spending more allowance.
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from pathlib import PurePosixPath
from typing import Any, Callable

from pydantic import ValidationError

from app.config import settings
from app.llm.prompts import (
    COMBINED_SYSTEM_INSTRUCTION,
    SYSTEM_INSTRUCTION,
    build_combined_review_prompt,
    build_review_prompt,
)
from app.llm.schemas import (
    COMBINED_CATEGORY_KEYS,
    AgentCategoryAnalysis,
    CombinedAnalysis,
    Finding,
    FindingSource,
    GeminiAnalysis,
    normalize_combined_category,
)

logger = logging.getLogger(__name__)

#: Stable Gemini model used when ``GEMINI_MODEL`` is unset.
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_ATTEMPTS = 3
MAX_OUTPUT_TOKENS = 8192
MAX_RETRY_DELAY_SECONDS = 8.0
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
RATE_LIMIT_STATUS_CODE = 429
STOP_FINISH_REASONS = frozenset(
    {"MAX_TOKENS", "SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"}
)

_FENCE_PATTERN = re.compile(r"^```(?:json|JSON)?\s*|\s*```$")

NOT_CONFIGURED_MESSAGE = (
    "Gemini analysis is not configured. Set GEMINI_API_KEY in the backend "
    "environment to enable AI findings."
)

QUOTA_EXCEEDED_MESSAGE = (
    "{provider} quota exceeded (HTTP 429): the free-tier rate limit for model "
    "'{model}' is exhausted, so no AI findings were produced. Static analysis "
    "findings are unaffected. Retry after the quota resets."
)


def quota_exceeded_message(
    model: str, remaining_seconds: float = 0.0, *, provider: str = "Gemini"
) -> str:
    """Build the operator-facing message for an exhausted provider quota."""
    message = QUOTA_EXCEEDED_MESSAGE.format(provider=provider, model=model)
    if remaining_seconds > 0:
        message += f" Gemini calls are paused for another {int(remaining_seconds)}s."
    return message


class _QuotaGate:
    """Process-wide pause after Gemini reports an exhausted quota.

    Retrying a 429 only burns more quota, so once a quota error is seen every
    Gemini call in this process short-circuits until the cooldown expires. The
    review then reports the failure honestly instead of hammering the API.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def block(self, seconds: float) -> None:
        with self._lock:
            self._blocked_until = max(
                self._blocked_until, time.monotonic() + max(seconds, 0.0)
            )

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._blocked_until = 0.0


_quota_gate = _QuotaGate()


def quota_cooldown_remaining() -> float:
    """Seconds left on the process-wide quota pause (0 when calls are allowed)."""
    return _quota_gate.remaining()


def reset_quota_state() -> None:
    """Clear the quota pause. Used by tests and by configuration reloads."""
    _quota_gate.reset()


class GeminiServiceError(RuntimeError):
    """Base class for every failure raised by the Gemini service.

    Messages are written for operators, are scrubbed of the API key, and are
    short enough to log or surface safely.
    """

    retryable = False

    def __init__(self, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable


class GeminiNotConfiguredError(GeminiServiceError):
    """Raised when no API key is configured or the SDK is unavailable."""


class GeminiTimeoutError(GeminiServiceError):
    """Raised when every attempt timed out."""

    retryable = True


class GeminiRateLimitError(GeminiServiceError):
    """Raised when Gemini reports an exhausted quota (HTTP 429).

    Never retried: an exhausted free-tier quota does not recover within a
    short backoff, and retrying only consumes more of the daily allowance.
    """

    retryable = False


class GeminiRequestRejectedError(GeminiServiceError):
    """Raised for non-retryable client errors such as a bad key or model id."""


class GeminiResponseError(GeminiServiceError):
    """Raised when the model response is blocked, empty, or unparseable."""


def _exception_types(module_name: str, *names: str) -> tuple[type[BaseException], ...]:
    """Resolve optional transport exception classes without hard dependencies."""
    try:
        module = __import__(module_name, fromlist=["__name__"])
    except ImportError:  # pragma: no cover - transport library absent
        return ()
    return tuple(
        exception_type
        for exception_type in (
            getattr(module, "exceptions", module).__dict__.get(name) for name in names
        )
        if isinstance(exception_type, type)
    )


_TIMEOUT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    *_exception_types("httpx", "TimeoutException"),
    *_exception_types("requests", "Timeout"),
)
_CONNECTION_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    *_exception_types("httpx", "TransportError"),
    *_exception_types("requests", "ConnectionError"),
)

try:  # The service is importable without the SDK; only calls need it.
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover - exercised only without google-genai
    genai_errors = None  # type: ignore[assignment]


def _basename(value: str | None) -> str:
    """Reduce a model-reported path to a bare file name."""
    if not value:
        return ""
    normalized = value.strip().replace("\\", "/")
    return PurePosixPath(normalized).name


def _status_name(value: Any) -> str:
    """Return the enum name for an SDK enum, or a trimmed string."""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value).strip() if value is not None else ""


def _describe_validation_error(error: ValidationError) -> str:
    details = []
    for item in error.errors()[:3]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "response"
        message = str(item.get("msg", "invalid value"))
        details.append(f"{location}: {message}"[:180])
    return "; ".join(details) or "unknown validation error"


def _strip_code_fence(text: str) -> str:
    return _FENCE_PATTERN.sub("", text.strip())


def _normalize_system_instruction(
    instruction: str | None,
) -> str | None:
    """Ensure system instruction is a string or None for GenerateContentConfig."""
    if instruction is None:
        return None
    return str(instruction)


class GeminiCodeReviewService:
    """Runs one Gemini review request and returns validated findings.

    The client is created lazily on first use and reused, so constructing the
    service is cheap. Calls are synchronous; FastAPI runs sync endpoints in a
    worker thread, which keeps the event loop free.

    Prompt building, JSON parsing, and the finding trust boundary are shared
    with :class:`~app.llm.openrouter_service.OpenRouterCodeReviewService`, which
    overrides the transport and the provider-specific labels below.
    """

    # Provider identity and error mapping. Subclasses replace these so every
    # message names the provider that actually failed.
    display_name = "Gemini"
    api_key_env_var = "GEMINI_API_KEY"
    model_env_var = "GEMINI_MODEL"
    not_configured_message = NOT_CONFIGURED_MESSAGE
    service_error = GeminiServiceError
    not_configured_error = GeminiNotConfiguredError
    request_rejected_error = GeminiRequestRejectedError
    response_error = GeminiResponseError
    rate_limit_error = GeminiRateLimitError
    timeout_error = GeminiTimeoutError
    quota_gate = _quota_gate

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        quota_cooldown_seconds: float = 300.0,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self.model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.timeout_seconds = max(float(timeout_seconds), 0.1)
        self.max_attempts = max(int(max_attempts), 1)
        self.quota_cooldown_seconds = max(float(quota_cooldown_seconds), 0.0)
        self._client = client
        self._sleep = sleep
        self._random = random_value

    def __repr__(self) -> str:
        # Never include the key, even if the object is logged by accident.
        return (
            f"GeminiCodeReviewService(model={self.model!r}, "
            f"configured={self.is_configured}, timeout_seconds={self.timeout_seconds!r})"
        )

    @property
    def is_configured(self) -> bool:
        return self._api_key is not None

    @classmethod
    def from_settings(cls, **overrides: Any) -> "GeminiCodeReviewService":
        """Build a service from the backend environment configuration."""
        return cls(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_attempts=settings.gemini_max_attempts,
            quota_cooldown_seconds=settings.gemini_quota_cooldown_seconds,
            **overrides,
        )

    def analyze(
        self,
        *,
        code: str,
        language: str,
        filename: str | None = None,
        system_instruction: str | None = None,
    ) -> GeminiAnalysis:
        """Review ``code`` and return validated findings.

        The optional ``system_instruction`` overrides the default system prompt
        if an agent wants to customize the behaviour (for example, domain-specific
        rules).

        Raises a :class:`GeminiServiceError` subclass on failure; callers should
        treat findings as suggestions, never as verified fixes.
        """
        if not self.is_configured:
            raise self.not_configured_error(self.not_configured_message)
        if not code.strip():
            raise self.request_rejected_error("No code was submitted for analysis.")

        prompt = build_review_prompt(code=code, language=language, filename=filename)
        raw_text = self._generate(prompt, system_instruction=system_instruction)
        analysis = self._parse(
            raw_text,
            total_lines=code.count("\n") + 1,
            filename=filename,
        )
        return analysis.model_copy(update={"model_name": self.model})

    def analyze_combined(
        self,
        *,
        code: str,
        language: str,
        filename: str | None = None,
        system_instruction: str | None = None,
    ) -> CombinedAnalysis:
        """Review ``code`` once for all four agent categories.

        One Gemini request fills the bug, security, performance, and quality
        sections, which uses a quarter of the requests of running four agents
        separately. The response is validated and sanitized with the same trust
        boundary as :meth:`analyze`; ``categories`` always contains all four
        canonical keys, with empty sections where a category is clean.

        Raises a :class:`GeminiServiceError` subclass on failure; callers must
        treat that as "no AI findings", never as a clean review.
        """
        if not self.is_configured:
            raise self.not_configured_error(self.not_configured_message)
        if not code.strip():
            raise self.request_rejected_error("No code was submitted for analysis.")

        prompt = build_combined_review_prompt(
            code=code, language=language, filename=filename
        )
        raw_text = self._generate(
            prompt,
            system_instruction=system_instruction or COMBINED_SYSTEM_INSTRUCTION,
        )
        analysis = self._parse_combined(
            raw_text,
            total_lines=code.count("\n") + 1,
            filename=filename,
        )
        return analysis.model_copy(update={"model_name": self.model})

    # ------------------------------------------------------------------
    # Model calls
    # ------------------------------------------------------------------

    def _generate(self, prompt: str, system_instruction: str | None = None) -> str:
        """Call the provider, retrying transient failures with exponential backoff."""
        remaining = self.quota_gate.remaining()
        if remaining > 0:
            # Do not spend another request while the quota is known-exhausted.
            raise self.rate_limit_error(
                quota_exceeded_message(
                    self.model, remaining, provider=self.display_name
                )
            )

        client = self._get_client()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._request(client, prompt, system_instruction)
                return self._extract_text(response)
            except GeminiServiceError as exc:
                if not exc.retryable or attempt >= self.max_attempts:
                    raise
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Gemini attempt %s/%s failed (%s); retrying in %.2fs",
                    attempt,
                    self.max_attempts,
                    type(exc).__name__,
                    delay,
                )
                self._sleep(delay)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        """Create a Gemini client with a bounded per-request timeout.

        SDK-level retries are disabled so retry behaviour lives in one place and
        cannot multiply with the retry loop above.
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise GeminiNotConfiguredError(
                "The google-genai package is not installed. Run "
                "'pip install -r requirements.txt' in backend/."
            ) from exc

        http_options = types.HttpOptions(
            timeout=int(self.timeout_seconds * 1000),  # the SDK expects milliseconds
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        return genai.Client(api_key=self._api_key, http_options=http_options)

    def _request(
        self,
        client: Any,
        prompt: str,
        system_instruction: str | None = None,
    ) -> Any:
        """Perform one SDK call, translating failures into service errors."""
        try:
            config = self._generation_config(system_instruction=system_instruction)
            return client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except GeminiServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - every SDK failure is translated
            raise self._translate_error(exc) from None

    def _translate_error(self, exc: BaseException) -> GeminiServiceError:
        """Map an SDK, HTTP, or transport failure to a clear service error."""
        if genai_errors is not None and isinstance(exc, genai_errors.APIError):
            code = getattr(exc, "code", None)
            detail = self._scrub(getattr(exc, "message", "") or "")
            suffix = f" {detail}" if detail else ""
            if code == RATE_LIMIT_STATUS_CODE:
                # Record the pause so no other agent or review keeps spending
                # requests against an exhausted quota. Not retryable.
                self.quota_gate.block(self.quota_cooldown_seconds)
                return self.rate_limit_error(
                    quota_exceeded_message(
                        self.model, provider=self.display_name
                    )
                    + suffix,
                    retryable=False,
                )
            if code in (401, 403):
                return self.request_rejected_error(
                    f"{self.display_name} rejected the request (HTTP {code}). "
                    f"Check that {self.api_key_env_var} is valid and allowed to "
                    f"use {self.model}.{suffix}"
                )
            if code == 404:
                return self.request_rejected_error(
                    f"{self.display_name} model '{self.model}' is not available "
                    f"(HTTP 404). Set {self.model_env_var} to a supported "
                    f"model.{suffix}"
                )
            if code == 400:
                return self.request_rejected_error(
                    f"{self.display_name} rejected the review request "
                    f"(HTTP 400).{suffix}"
                )
            if code in RETRYABLE_STATUS_CODES:
                return self.service_error(
                    f"{self.display_name} is temporarily unavailable "
                    f"(HTTP {code}).{suffix}",
                    retryable=True,
                )
            return self.service_error(
                f"{self.display_name} request failed (HTTP {code}).{suffix}"
            )

        if isinstance(exc, _TIMEOUT_EXCEPTIONS):
            return self.timeout_error(
                f"{self.display_name} did not respond within "
                f"{self.timeout_seconds:g} seconds."
            )
        if isinstance(exc, _CONNECTION_EXCEPTIONS):
            return self.service_error(
                f"Could not reach the {self.display_name} API.", retryable=True
            )
        return self.service_error(
            f"Unexpected {self.display_name} client failure "
            f"({type(exc).__name__})."
        )

    def _scrub(self, text: str) -> str:
        """Remove the API key from any text that may be logged or returned."""
        if not text:
            return ""
        if self._api_key and self._api_key in text:
            text = text.replace(self._api_key, "[redacted]")
        return text[:400].strip()

    def _generation_config(self, system_instruction: str | None = None) -> Any:
        options: dict[str, Any] = {
            "response_mime_type": "application/json",
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        sys_inst = _normalize_system_instruction(system_instruction) or SYSTEM_INSTRUCTION
        options["system_instruction"] = sys_inst
        try:
            from google.genai import types
        except ImportError:  # pragma: no cover - SDK absent, dict is still valid
            return options
        return types.GenerateContentConfig(**options)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped to keep requests bounded."""
        base = min(0.5 * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SECONDS)
        return round(base * (0.5 + self._random()), 3)

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    def _extract_text(self, response: Any) -> str:
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = _status_name(getattr(feedback, "block_reason", None))
        if block_reason:
            raise self.response_error(
                f"{self.display_name} blocked the request ({block_reason}). "
                "No findings were produced."
            )

        candidates = getattr(response, "candidates", None) or []
        finish_reason = ""
        if candidates:
            finish_reason = _status_name(getattr(candidates[0], "finish_reason", None))
        if finish_reason in STOP_FINISH_REASONS:
            raise self.response_error(
                f"{self.display_name} stopped before returning a complete "
                f"review ({finish_reason})."
            )

        try:
            text = response.text
        except (AttributeError, ValueError):  # SDK raises when there are no parts
            text = None
        if not isinstance(text, str) or not text.strip():
            raise self.response_error(
                f"{self.display_name} returned an empty response."
            )
        return text

    def _parse(self, raw_text: str, *, total_lines: int, filename: str | None) -> GeminiAnalysis:
        payload = self._load_json(raw_text)
        try:
            analysis = GeminiAnalysis.model_validate(payload)
        except ValidationError as exc:
            detail = _describe_validation_error(exc)
            raise self.response_error(
                f"{self.display_name} returned findings that failed validation: "
                f"{detail}"
            ) from None
        return self._sanitize(analysis, total_lines=total_lines, filename=filename)

    # ------------------------------------------------------------------
    # Combined (four-category) response handling
    # ------------------------------------------------------------------

    def _parse_combined(
        self, raw_text: str, *, total_lines: int, filename: str | None
    ) -> CombinedAnalysis:
        payload = self._load_json(raw_text)
        analysis = self._build_combined_analysis(payload)
        return self._sanitize_combined(
            analysis, total_lines=total_lines, filename=filename
        )

    def _build_combined_analysis(self, payload: dict[str, Any]) -> CombinedAnalysis:
        """Turn a raw combined payload into four canonical category sections."""
        summary = payload.get("summary")
        if not isinstance(summary, str):
            summary = ""
        warnings: list[str] = []
        sections: dict[str, AgentCategoryAnalysis] = {
            key: AgentCategoryAnalysis() for key in COMBINED_CATEGORY_KEYS
        }

        raw_categories = payload.get("categories")
        if raw_categories is None and "findings" in payload:
            # Lenient fallback: a flat findings list grouped by each finding's
            # own category. Still one request, still four agent results.
            return self._combine_flat_findings(
                payload, summary=summary, warnings=warnings
            )

        if not isinstance(raw_categories, dict):
            raise self.response_error(
                f"{self.display_name} returned JSON without a 'categories' "
                "object, so the four-category review could not be read."
            )

        for raw_key, raw_section in raw_categories.items():
            key = normalize_combined_category(raw_key)
            if key is None:
                warnings.append(f"Ignored unknown review category '{raw_key}'.")
                continue

            if isinstance(raw_section, list):
                raw_section = {"summary": "", "findings": raw_section}
            elif isinstance(raw_section, str):
                raw_section = {"summary": raw_section, "findings": []}

            try:
                section = AgentCategoryAnalysis.model_validate(raw_section)
            except ValidationError as exc:
                detail = _describe_validation_error(exc)
                raise self.response_error(
                    f"{self.display_name} returned a '{key}' category that "
                    f"failed validation: {detail}"
                ) from None

            for finding in section.findings:
                declared = normalize_combined_category(finding.category)
                if declared is not None and declared != key:
                    warnings.append(
                        f"Finding '{finding.id}' was labeled '{finding.category}' "
                        f"but reported under '{key}'; it was filed under '{key}'."
                    )

            existing = sections[key]
            combined_summary = " ".join(
                part for part in (existing.summary, section.summary) if part
            )
            sections[key] = AgentCategoryAnalysis(
                summary=combined_summary,
                findings=[*existing.findings, *section.findings],
            )

        return CombinedAnalysis(summary=summary, categories=sections, warnings=warnings)

    def _combine_flat_findings(
        self, payload: dict[str, Any], *, summary: str, warnings: list[str]
    ) -> CombinedAnalysis:
        """Group a flat ``findings`` list into the four canonical categories."""
        raw_findings = payload.get("findings")
        if not isinstance(raw_findings, list):
            raise self.response_error(
                f"{self.display_name} returned a 'findings' value that is not "
                "a list, so no findings could be read."
            )

        sections: dict[str, AgentCategoryAnalysis] = {
            key: AgentCategoryAnalysis() for key in COMBINED_CATEGORY_KEYS
        }
        for raw_finding in raw_findings:
            try:
                finding = Finding.model_validate(raw_finding)
            except ValidationError as exc:
                detail = _describe_validation_error(exc)
                raise self.response_error(
                    f"{self.display_name} returned a finding that failed "
                    f"validation: {detail}"
                ) from None
            key = normalize_combined_category(finding.category)
            if key is None:
                warnings.append(
                    f"Dropped finding '{finding.id}': category "
                    f"'{finding.category}' is not a review category."
                )
                continue
            sections[key].findings.append(finding)

        return CombinedAnalysis(summary=summary, categories=sections, warnings=warnings)

    def _sanitize_combined(
        self,
        analysis: CombinedAnalysis,
        *,
        total_lines: int,
        filename: str | None,
    ) -> CombinedAnalysis:
        """Apply the :meth:`_sanitize` trust boundary to every category."""
        warnings = list(analysis.warnings)
        categories: dict[str, AgentCategoryAnalysis] = {}
        seen_ids: set[str] = set()

        for key in COMBINED_CATEGORY_KEYS:
            section = analysis.categories.get(key) or AgentCategoryAnalysis()
            sanitized = self._sanitize(
                GeminiAnalysis(summary=section.summary, findings=section.findings),
                total_lines=total_lines,
                filename=filename,
            )
            warnings.extend(sanitized.warnings)

            findings: list[Finding] = []
            for finding in sanitized.findings:
                identifier = finding.id
                if identifier in seen_ids:
                    suffix = 2
                    while f"{finding.id}-{suffix}" in seen_ids:
                        suffix += 1
                    identifier = f"{finding.id}-{suffix}"
                    warnings.append(
                        f"Duplicate finding id '{finding.id}' renamed to "
                        f"'{identifier}'."
                    )
                seen_ids.add(identifier)
                findings.append(
                    finding.model_copy(update={"id": identifier, "category": key})
                )

            categories[key] = AgentCategoryAnalysis(
                summary=sanitized.summary, findings=findings
            )

        return analysis.model_copy(
            update={"categories": categories, "warnings": warnings}
        )

    def _load_json(self, raw_text: str) -> dict[str, Any]:
        cleaned = _strip_code_fence(raw_text)
        candidates = [cleaned]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= start < end:
            candidates.append(cleaned[start : end + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
            raise self.response_error(
                f"{self.display_name} returned JSON that is not an object with "
                "a findings list."
            )

        raise self.response_error(
            f"{self.display_name} returned malformed JSON, so no findings "
            "could be read."
        )

    def _sanitize(
        self,
        analysis: GeminiAnalysis,
        *,
        total_lines: int,
        filename: str | None,
    ) -> GeminiAnalysis:
        """Enforce the trust boundary on model output before returning it."""
        warnings = list(analysis.warnings)
        findings: list[Finding] = []
        seen_ids: set[str] = set()

        for finding in analysis.findings:
            if finding.start_line > total_lines or finding.end_line > total_lines:
                warnings.append(
                    f"Dropped finding '{finding.id}': line range "
                    f"{finding.start_line}-{finding.end_line} is outside the "
                    f"{total_lines}-line submission."
                )
                continue

            source = finding.source
            if source is FindingSource.STATIC_ANALYSIS:
                source = FindingSource.AI_SUGGESTION
                warnings.append(
                    f"Finding '{finding.id}' was labeled static_analysis by the model, "
                    "but no static analyzer confirmed it, so it was relabeled as an ai_suggestion."
                )

            identifier = finding.id
            if identifier in seen_ids:
                suffix = 2
                while f"{finding.id}-{suffix}" in seen_ids:
                    suffix += 1
                identifier = f"{finding.id}-{suffix}"
                warnings.append(
                    f"Duplicate finding id '{finding.id}' renamed to '{identifier}'."
                )
            seen_ids.add(identifier)

            findings.append(
                finding.model_copy(
                    update={
                        "id": identifier,
                        "source": source,
                        "file": _basename(finding.file) or _basename(filename) or "submitted_code",
                    }
                )
            )

        return analysis.model_copy(update={"findings": findings, "warnings": warnings})


_service: GeminiCodeReviewService | None = None


def get_gemini_service() -> GeminiCodeReviewService:
    """Return the process-wide service, created from settings on first use."""
    global _service
    if _service is None:
        _service = GeminiCodeReviewService.from_settings()
    return _service


def reset_gemini_service() -> None:
    """Drop the cached service so the next call re-reads configuration."""
    global _service
    _service = None