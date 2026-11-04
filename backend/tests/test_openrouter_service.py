"""OpenRouter service tests.

Every test routes HTTP through ``httpx.MockTransport`` (or a fake service), so
the suite never contacts OpenRouter and never consumes real API quota.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

import app.agents.orchestrator as orchestrator
from app.config import settings
from app.llm import provider
from app.llm.client import get_llm_client
from app.llm.gemini_service import GeminiServiceError
from app.llm.openrouter_service import (
    CHAT_COMPLETIONS_PATH,
    DEFAULT_APP_TITLE,
    DEFAULT_HTTP_REFERER,
    DEFAULT_MODEL,
    OpenRouterCodeReviewService,
    OpenRouterNotConfiguredError,
    OpenRouterRateLimitError,
    OpenRouterRequestRejectedError,
    OpenRouterResponseError,
    OpenRouterTimeoutError,
)
from app.llm.schemas import COMBINED_CATEGORY_KEYS, FindingSource

API_KEY = "sk-or-test-key-should-never-leak"
CODE = "def divide(a, b):\n    return a / b\n"
LANGUAGE = "python"
FILENAME = "math_utils.py"


def finding(*, id: str = "div-zero", category: str = "bug") -> dict[str, Any]:
    return {
        "id": id,
        "title": "Division without a zero check",
        "description": "b may be zero.",
        "severity": "High",
        "category": category,
        "file": FILENAME,
        "start_line": 2,
        "end_line": 2,
        "suggested_fix": "Raise ValueError when b == 0.",
        "confidence": 0.9,
        "explanation": "Dividing by zero raises an unhandled exception.",
        "source": "ai_suggestion",
    }


def model_json(
    categories: dict[str, Any] | None = None,
    *,
    summary: str = "One bug found.",
) -> str:
    sections: dict[str, Any] = {
        key: {"summary": f"{key} is clean.", "findings": []}
        for key in COMBINED_CATEGORY_KEYS
    }
    sections.update(categories or {})
    return json.dumps({"summary": summary, "categories": sections})


def completion_payload(
    content: str | None = None,
    *,
    model: str = "meta-llama/llama-3.3-70b-instruct:free",
    finish_reason: str = "stop",
) -> dict[str, Any]:
    if content is None:
        content = model_json(
            {"bug": {"summary": "One bug.", "findings": [finding()]}}
        )
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }


def json_response(payload: Any, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def build_service(
    handler,
    *,
    api_key: str = API_KEY,
    max_attempts: int = 1,
    model: str = DEFAULT_MODEL,
    base_url: str = "https://openrouter.ai/api/v1",
    **overrides: Any,
) -> tuple[OpenRouterCodeReviewService, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(recording_handler))
    service = OpenRouterCodeReviewService(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=1.0,
        max_attempts=max_attempts,
        client=client,
        sleep=lambda _seconds: None,
        random_value=lambda: 0.0,
        **overrides,
    )
    return service, requests


def analyze_combined(service: OpenRouterCodeReviewService):
    return service.analyze_combined(code=CODE, language=LANGUAGE, filename=FILENAME)


# ---------------------------------------------------------------------------
# Successful combined review
# ---------------------------------------------------------------------------


class TestOpenRouterSuccess:
    def test_one_request_fills_all_four_categories_with_expected_headers(self) -> None:
        service, requests = build_service(lambda _request: json_response(completion_payload()))

        analysis = analyze_combined(service)

        assert len(requests) == 1
        request = requests[0]
        assert request.method == "POST"
        assert str(request.url) == (
            "https://openrouter.ai/api/v1" + CHAT_COMPLETIONS_PATH
        )
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert request.headers["content-type"] == "application/json"
        assert request.headers["http-referer"] == DEFAULT_HTTP_REFERER
        assert request.headers["x-openrouter-title"] == DEFAULT_APP_TITLE

        body = json.loads(request.content)
        assert body["model"] == DEFAULT_MODEL
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["role"] == "system"
        assert "four review agents" in body["messages"][0]["content"]
        assert body["messages"][1]["role"] == "user"
        assert "def divide" in body["messages"][1]["content"]
        assert "--- END SUBMITTED CODE ---" in body["messages"][1]["content"]
        # The credential is only in the header, never in the prompt.
        assert API_KEY not in body["messages"][1]["content"]

        assert set(analysis.categories) == set(COMBINED_CATEGORY_KEYS)
        assert [f.id for f in analysis.categories["bug"].findings] == ["div-zero"]
        assert analysis.categories["bug"].findings[0].source is FindingSource.AI_SUGGESTION
        assert analysis.categories["security"].findings == []
        assert analysis.model_name == DEFAULT_MODEL

    def test_actual_routed_model_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        service, _ = build_service(
            lambda _request: json_response(
                completion_payload(model="qwen/qwen3-4b:free")
            )
        )

        with caplog.at_level(logging.INFO, logger="app.llm.openrouter_service"):
            analysis = analyze_combined(service)

        assert analysis.categories["bug"].findings
        assert "qwen/qwen3-4b:free" in caplog.text
        assert DEFAULT_MODEL in caplog.text
        assert API_KEY not in caplog.text

    def test_missing_returned_model_is_handled_with_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        payload = completion_payload()
        del payload["model"]
        service, _ = build_service(lambda _request: json_response(payload))

        with caplog.at_level(logging.WARNING, logger="app.llm.openrouter_service"):
            analysis = analyze_combined(service)

        assert analysis.categories["bug"].findings
        assert "did not report the model" in caplog.text

    def test_per_agent_analyze_uses_the_individual_finding_schema(self) -> None:
        payload = {
            "summary": "One bug.",
            "findings": [finding()],
        }
        service, requests = build_service(
            lambda _request: json_response(
                completion_payload(json.dumps(payload))
            )
        )

        analysis = service.analyze(code=CODE, language=LANGUAGE, filename=FILENAME)

        assert len(requests) == 1
        assert [f.id for f in analysis.findings] == ["div-zero"]
        assert analysis.model_name == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Provider failures
# ---------------------------------------------------------------------------


class TestOpenRouterFailures:
    def test_429_is_not_retried_and_pauses_further_calls(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(
                {"error": {"code": 429, "message": "free-tier rate limit reached"}},
                status_code=429,
            ),
            max_attempts=3,
        )

        with pytest.raises(OpenRouterRateLimitError) as error:
            analyze_combined(service)

        assert "429" in str(error.value)
        assert "quota exceeded" in str(error.value)
        assert "rate limit reached" in str(error.value)
        assert len(requests) == 1

        # A second call fails fast without spending another request.
        with pytest.raises(OpenRouterRateLimitError, match="paused"):
            analyze_combined(service)
        assert len(requests) == 1

    def test_invalid_api_key_is_reported_without_leaking_it(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(
                {"error": {"code": 401, "message": f"invalid key {API_KEY}"}},
                status_code=401,
            )
        )

        with pytest.raises(OpenRouterRequestRejectedError, match="OPENROUTER_API_KEY") as error:
            analyze_combined(service)

        message = str(error.value)
        assert "401" in message
        assert API_KEY not in message
        assert "[redacted]" in message
        assert len(requests) == 1

    def test_unknown_model_is_reported_with_a_hint(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(
                {"error": {"code": 404, "message": "model not found"}},
                status_code=404,
            )
        )

        with pytest.raises(OpenRouterRequestRejectedError, match="OPENROUTER_MODEL"):
            analyze_combined(service)

    def test_bad_request_is_not_retried(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(
                {"error": {"code": 400, "message": "invalid request"}},
                status_code=400,
            ),
            max_attempts=3,
        )

        with pytest.raises(OpenRouterRequestRejectedError, match="HTTP 400"):
            analyze_combined(service)

        assert len(requests) == 1

    def test_server_error_is_retried_then_succeeds(self) -> None:
        outcomes = [
            json_response({"error": {"message": "unavailable"}}, status_code=503),
            json_response(completion_payload()),
        ]
        service, requests = build_service(
            lambda _request: outcomes.pop(0), max_attempts=2
        )

        analysis = analyze_combined(service)

        assert len(requests) == 2
        assert analysis.categories["bug"].findings

    def test_timeout_is_retried_and_reported(self) -> None:
        def timed_out(_request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        service, requests = build_service(timed_out, max_attempts=2)

        with pytest.raises(OpenRouterTimeoutError, match="did not respond"):
            analyze_combined(service)

        assert len(requests) == 2

    def test_transport_failure_is_reported_and_retried(self) -> None:
        def unreachable(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        service, requests = build_service(unreachable, max_attempts=2)

        with pytest.raises(GeminiServiceError, match="Could not reach"):
            analyze_combined(service)

        assert len(requests) == 2

    def test_empty_content_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(completion_payload("   "))
        )

        with pytest.raises(OpenRouterResponseError, match="empty response"):
            analyze_combined(service)

    def test_missing_choices_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: json_response({"model": DEFAULT_MODEL, "choices": []})
        )

        with pytest.raises(OpenRouterResponseError, match="no choices"):
            analyze_combined(service)

    def test_error_payload_with_http_200_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: json_response({"error": {"message": "upstream exploded"}})
        )

        with pytest.raises(OpenRouterResponseError, match="upstream exploded"):
            analyze_combined(service)

    def test_non_json_body_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: httpx.Response(200, text="<html>gateway</html>")
        )

        with pytest.raises(OpenRouterResponseError, match="not valid JSON"):
            analyze_combined(service)

    def test_truncated_response_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(
                completion_payload(finish_reason="length")
            )
        )

        with pytest.raises(OpenRouterResponseError, match="complete review"):
            analyze_combined(service)

    def test_content_filtered_response_is_reported_as_blocked(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(
                completion_payload(finish_reason="content_filter")
            )
        )

        with pytest.raises(OpenRouterResponseError, match="blocked"):
            analyze_combined(service)

    def test_malformed_model_json_is_reported(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(completion_payload("not json at all"))
        )

        with pytest.raises(OpenRouterResponseError, match="malformed JSON"):
            analyze_combined(service)

    def test_service_without_a_key_refuses_to_call_out(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(completion_payload()), api_key=""
        )

        with pytest.raises(OpenRouterNotConfiguredError, match="OPENROUTER_API_KEY"):
            analyze_combined(service)

        assert requests == []

    def test_empty_code_is_rejected_before_any_call(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(completion_payload())
        )

        with pytest.raises(GeminiServiceError, match="No code"):
            service.analyze_combined(code="   \n", language=LANGUAGE, filename=None)

        assert requests == []

    def test_repr_does_not_expose_the_api_key(self) -> None:
        service, _ = build_service(
            lambda _request: json_response(completion_payload())
        )

        assert API_KEY not in repr(service)
        assert "configured=True" in repr(service)


# ---------------------------------------------------------------------------
# Configuration and provider selection
# ---------------------------------------------------------------------------


class TestOpenRouterConfiguration:
    def test_from_settings_reads_the_environment(self) -> None:
        service = OpenRouterCodeReviewService.from_settings()

        assert service.model == settings.openrouter_model
        assert service.base_url == settings.openrouter_base_url
        assert service.max_attempts == settings.openrouter_max_attempts
        # conftest blanks OPENROUTER_API_KEY, so the service must refuse to run.
        assert service.is_configured is False

    def test_headers_use_configured_attribution(self) -> None:
        service, requests = build_service(
            lambda _request: json_response(completion_payload()),
            http_referer="https://example.com/review",
            app_title="Example Reviewer",
        )

        analyze_combined(service)

        assert requests[0].headers["http-referer"] == "https://example.com/review"
        assert requests[0].headers["x-openrouter-title"] == "Example Reviewer"

    def test_openrouter_is_preferred_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configured = dataclasses.replace(
            settings,
            default_llm_provider="openrouter",
            openrouter_api_key="or-key",
            gemini_api_key="gem-key",
        )
        monkeypatch.setattr(provider, "settings", configured)
        monkeypatch.setattr("app.llm.client.settings", configured)

        assert provider.resolve_provider() == "openrouter"
        client = get_llm_client()
        assert client.provider == "openrouter"
        assert client.is_available is True
        assert settings.openrouter_model in client.message

    def test_gemini_is_used_when_the_openrouter_key_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configured = dataclasses.replace(
            settings,
            default_llm_provider="openrouter",
            openrouter_api_key=None,
            gemini_api_key="gem-key",
        )
        monkeypatch.setattr(provider, "settings", configured)
        monkeypatch.setattr("app.llm.client.settings", configured)

        assert provider.resolve_provider() == "gemini"
        client = get_llm_client()
        assert client.provider == "gemini"
        assert client.is_available is True

    def test_get_review_service_builds_and_caches_the_active_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configured = dataclasses.replace(
            settings,
            default_llm_provider="openrouter",
            openrouter_api_key="or-key",
            gemini_api_key=None,
        )
        monkeypatch.setattr(provider, "settings", configured)
        built: list[object] = []

        class FakeOpenRouterService:
            @classmethod
            def from_settings(cls):
                instance = object()
                built.append(instance)
                return instance

        monkeypatch.setattr(
            provider, "OpenRouterCodeReviewService", FakeOpenRouterService
        )
        provider.reset_review_service()
        try:
            first = provider.get_review_service()
            second = provider.get_review_service()
        finally:
            provider.reset_review_service()

        assert first is second
        assert len(built) == 1

    def test_nothing_configured_reports_pending_with_both_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        configured = dataclasses.replace(
            settings,
            default_llm_provider="openrouter",
            openrouter_api_key=None,
            gemini_api_key=None,
        )
        monkeypatch.setattr(provider, "settings", configured)
        monkeypatch.setattr("app.llm.client.settings", configured)

        assert provider.resolve_provider() is None
        client = get_llm_client()
        assert client.is_available is False
        assert client.status == "not_configured"
        assert "OPENROUTER_API_KEY" in client.message
        assert "GEMINI_API_KEY" in client.message


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------


class FailingCombinedService:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def analyze_combined(self, *, code: str, language: str, filename: str | None = None):
        self.calls += 1
        raise self.error


class TestOpenRouterOrchestratorIntegration:
    def test_quota_failure_never_fabricates_results_and_skips_the_fix_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.agents import combined_agent

        service = FailingCombinedService(
            OpenRouterRateLimitError(
                "OpenRouter quota exceeded (HTTP 429) for model 'openrouter/free'."
            )
        )
        monkeypatch.setattr(
            combined_agent, "get_gemini_service", lambda: service
        )
        monkeypatch.setattr(orchestrator, "run_static_analysis", lambda *args: [])
        fix_agent = MagicMock()
        monkeypatch.setattr(orchestrator, "_run_fix_agent", fix_agent)

        result = orchestrator.run_all_agents(
            CODE, LANGUAGE, FILENAME, review_mode="combined"
        )

        assert service.calls == 1
        assert result.status == "error"
        assert result.ai_suggestion_findings == 0
        primary = [r for r in result.agent_results if r.agent_id in COMBINED_CATEGORY_KEYS]
        assert len(primary) == 4
        assert all(r.status == "error" for r in primary)
        assert all("quota exceeded" in (r.error_message or "") for r in primary)
        fix_agent.assert_not_called()
        assert "quota exceeded" in result.summary
