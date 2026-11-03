"""Health endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_service_database_and_ai_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ALPHA CodeGuard AI API"
    assert body["database"] == "ok"
    assert body["llm"]["status"] == "not_configured"
    assert body["llm"]["configured"] is False
    assert "not configured" in body["llm"]["message"].lower()


def test_root_describes_service(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["health"] == "/health"
