"""Application configuration resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = BACKEND_DIR / "codeguard.db"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

# Load backend/.env when present. Existing environment variables take precedence,
# which keeps tests and container configuration deterministic.
load_dotenv(BACKEND_DIR / ".env")


def _split_origins(raw_value: str) -> tuple[str, ...]:
    origins = tuple(origin.strip() for origin in raw_value.split(",") if origin.strip())
    return origins or DEFAULT_CORS_ORIGINS


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


REVIEW_MODES = ("combined", "per_agent")
LLM_PROVIDERS = ("openrouter", "gemini")


def _review_mode(name: str, default: str) -> str:
    """Read the review mode, falling back to ``combined`` for unknown values."""
    raw_value = (os.getenv(name) or "").strip().lower()
    return raw_value if raw_value in REVIEW_MODES else default


def _llm_provider(name: str, default: str) -> str:
    """Read the preferred LLM provider, falling back for unknown values."""
    raw_value = (os.getenv(name) or "").strip().lower()
    return raw_value if raw_value in LLM_PROVIDERS else default


def _get_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_name: str
    version: str
    environment: str
    database_url: str
    cors_origins: tuple[str, ...]
    max_code_length: int
    llm_provider: str
    llm_api_key: str | None
    llm_model: str | None
    # Preferred AI provider ("openrouter" or "gemini"). The other provider is
    # used only when the preferred one has no API key configured.
    default_llm_provider: str
    # OpenRouter free-models router. The key stays server-side and is never
    # logged or returned by the API.
    openrouter_api_key: str | None
    openrouter_base_url: str
    openrouter_model: str
    openrouter_timeout_seconds: float
    openrouter_max_attempts: int
    openrouter_quota_cooldown_seconds: float
    openrouter_http_referer: str
    openrouter_app_title: str
    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_seconds: float
    gemini_max_attempts: int
    # "combined" sends one request for all four categories; "per_agent" runs
    # four independent requests (higher quota use).
    gemini_review_mode: str
    # How long to stop calling Gemini after an HTTP 429 quota error.
    gemini_quota_cooldown_seconds: float
    # Rate limiting (disable in automated tests so fixtures can register users).
    rate_limit_enabled: bool
    # Auth settings
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    # OAuth
    google_client_id: str | None
    google_client_secret: str | None
    google_redirect_uri: str
    github_client_id: str | None
    github_client_secret: str | None
    github_redirect_uri: str
    frontend_url: str


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL") or (
        f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    )
    secret_key = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production-please"
    return Settings(
        app_name="ALPHA CodeGuard AI API",
        version="0.3.0",
        environment=os.getenv("APP_ENV", "development"),
        database_url=database_url,
        cors_origins=_split_origins(
            os.getenv("CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS))
        ),
        max_code_length=_positive_int("MAX_CODE_LENGTH", 200_000),
        llm_provider=(os.getenv("LLM_PROVIDER") or "none").strip().lower(),
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL") or None,
        # DEFAULT_LLM_PROVIDER wins; the legacy LLM_PROVIDER is honored when it
        # names a real provider so older deployments keep working.
        default_llm_provider=_llm_provider(
            "DEFAULT_LLM_PROVIDER",
            _llm_provider("LLM_PROVIDER", "openrouter"),
        ),
        openrouter_api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip() or None,
        openrouter_base_url=(
            os.getenv("OPENROUTER_BASE_URL") or ""
        ).strip().rstrip("/")
        or "https://openrouter.ai/api/v1",
        openrouter_model=(os.getenv("OPENROUTER_MODEL") or "").strip()
        or "openrouter/free",
        openrouter_timeout_seconds=_positive_float("OPENROUTER_TIMEOUT_SECONDS", 45.0),
        openrouter_max_attempts=_positive_int("OPENROUTER_MAX_ATTEMPTS", 3),
        openrouter_quota_cooldown_seconds=_positive_float(
            "OPENROUTER_QUOTA_COOLDOWN_SECONDS", 300.0
        ),
        openrouter_http_referer=(
            os.getenv("OPENROUTER_HTTP_REFERER") or ""
        ).strip()
        or "https://code-guard-ai-rho.vercel.app",
        openrouter_app_title=(
            os.getenv("OPENROUTER_APP_TITLE") or ""
        ).strip()
        or "ALPHA CodeGuard AI",
        # Secrets stay server-side: the key is only ever read here and handed to
        # the Gemini client, never to a response, log line, or the frontend.
        gemini_api_key=(os.getenv("GEMINI_API_KEY") or "").strip() or None,
        gemini_model=(os.getenv("GEMINI_MODEL") or "").strip() or "gemini-3.8-flash",
        gemini_timeout_seconds=_positive_float("GEMINI_TIMEOUT_SECONDS", 45.0),
        gemini_max_attempts=_positive_int("GEMINI_MAX_ATTEMPTS", 3),
        gemini_review_mode=_review_mode("GEMINI_REVIEW_MODE", "combined"),
        gemini_quota_cooldown_seconds=_positive_float(
            "GEMINI_QUOTA_COOLDOWN_SECONDS", 300.0
        ),
        rate_limit_enabled=_get_bool("RATE_LIMIT_ENABLED", True),
        secret_key=secret_key,
        algorithm=os.getenv("ALGORITHM", "HS256"),
        access_token_expire_minutes=_positive_int("ACCESS_TOKEN_EXPIRE_MINUTES", 30),
        refresh_token_expire_days=_positive_int("REFRESH_TOKEN_EXPIRE_DAYS", 7),
        google_client_id=(os.getenv("GOOGLE_CLIENT_ID") or "").strip() or None,
        google_client_secret=(os.getenv("GOOGLE_CLIENT_SECRET") or "").strip() or None,
        google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI") or "http://localhost:8000/api/auth/google/callback",
        github_client_id=(os.getenv("GITHUB_CLIENT_ID") or "").strip() or None,
        github_client_secret=(os.getenv("GITHUB_CLIENT_SECRET") or "").strip() or None,
        github_redirect_uri=os.getenv("GITHUB_REDIRECT_URI") or "http://localhost:8000/api/auth/github/callback",
        frontend_url=os.getenv("FRONTEND_URL") or "http://localhost:5173",
    )


settings = load_settings()
