"""Shared test fixtures. Environment is configured before the app is imported."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

_TEMP_DIR = Path(tempfile.mkdtemp(prefix="codeguard-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEMP_DIR / 'test.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
os.environ["MAX_CODE_LENGTH"] = "200000"
# Tests never call Gemini. An empty value keeps a developer's local key out of
# the test run and still lets python-dotenv find nothing to load.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = "gemini-3.8-flash"
os.environ["GEMINI_TIMEOUT_SECONDS"] = "5"
os.environ["GEMINI_MAX_ATTEMPTS"] = "2"
# Fixtures register several accounts per run; per-IP auth limits would block them.
os.environ["RATE_LIMIT_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator:
    """A direct ORM session for service-level tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register_user(client: TestClient, email: str | None = None) -> dict:
    """Create an account and return the token payload."""
    address = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test User",
            "email": address,
            "password": "Password123",
            "confirm_password": "Password123",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    token = register_user(client)["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_client(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    """A client that sends the account's bearer token on every request."""
    client.headers.update(auth_headers)
    return client
