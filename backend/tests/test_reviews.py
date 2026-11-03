"""Review submission and history endpoint tests."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.config import settings

SAMPLE_CODE = "def add(a, b):\n    return a + b\n"


def register_user(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test User",
            "email": email,
            "password": "Password123",
            "confirm_password": "Password123",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client: TestClient, **overrides: object):
    payload: dict[str, object] = {
        "code": SAMPLE_CODE,
        "language": "python",
        "filename": "math_utils.py",
    }
    payload.update(overrides)
    return client.post("/api/review", json=payload)


def test_review_endpoints_require_authentication(client: TestClient) -> None:
    assert client.post("/api/review", json={"code": "x = 1", "language": "python"}).status_code == 401
    assert client.get("/api/reviews").status_code == 401
    assert client.get("/api/reviews/rev_anything").status_code == 401


def test_create_review_returns_pending_without_findings(auth_client: TestClient) -> None:
    response = submit(auth_client)

    assert response.status_code == 201
    body = response.json()
    # Without GEMINI_API_KEY the review is stored as pending, never fabricated.
    assert body["status"] in ("pending", "completed", "completed_with_errors")
    assert body["issues"] == []
    assert body["counts"] == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0}
    assert body["language"] == "python"
    assert body["language_label"] == "Python"
    assert body["filename"] == "math_utils.py"
    assert body["characters"] == len(SAMPLE_CODE)
    assert body["lines"] == SAMPLE_CODE.count("\n") + 1
    assert len(body["agents"]) == 5
    assert sum(agent["findings"] for agent in body["agents"]) == 0


def test_created_review_is_persisted_and_retrievable(auth_client: TestClient) -> None:
    created = submit(auth_client).json()

    response = auth_client.get(f"/api/reviews/{created['id']}")

    assert response.status_code == 200
    stored = response.json()
    assert stored["id"] == created["id"]
    assert stored["code"] == SAMPLE_CODE
    assert stored["status"] in ("pending", "completed", "completed_with_errors")


def test_reviews_are_scoped_to_their_owner(client: TestClient) -> None:
    owner = register_user(client, "owner@example.com")
    owner_client = TestClient(client.app, headers={"Authorization": f"Bearer {owner['access_token']}"})
    created = owner_client.post(
        "/api/review",
        json={"code": SAMPLE_CODE, "language": "python"},
    ).json()

    other = register_user(client, "other@example.com")
    other_client = TestClient(client.app, headers={"Authorization": f"Bearer {other['access_token']}"})

    # Another account can neither read nor list the review.
    assert other_client.get(f"/api/reviews/{created['id']}").status_code == 404
    listing = other_client.get("/api/reviews").json()
    assert listing["total"] == 0
    assert listing["items"] == []

    assert owner_client.get(f"/api/reviews/{created['id']}").status_code == 200
    assert owner_client.get("/api/reviews").json()["total"] == 1


def test_fix_decision_requires_owner_and_validates_input(client: TestClient) -> None:
    owner = register_user(client, "decision-owner@example.com")
    owner_client = TestClient(client.app, headers={"Authorization": f"Bearer {owner['access_token']}"})
    created = owner_client.post(
        "/api/review",
        json={"code": SAMPLE_CODE, "language": "python"},
    ).json()

    # Unknown decision values are rejected rather than stored verbatim.
    assert (
        owner_client.post(
            f"/api/reviews/{created['id']}/fix-decision",
            params={"decision": "maybe", "finding_id": "f1"},
        ).status_code
        == 422
    )
    # Unknown finding ids are rejected.
    assert (
        owner_client.post(
            f"/api/reviews/{created['id']}/fix-decision",
            params={"decision": "accepted", "finding_id": "missing"},
        ).status_code
        == 404
    )

    other = register_user(client, "decision-other@example.com")
    other_client = TestClient(client.app, headers={"Authorization": f"Bearer {other['access_token']}"})
    assert (
        other_client.post(
            f"/api/reviews/{created['id']}/fix-decision",
            params={"decision": "accepted", "finding_id": "f1"},
        ).status_code
        == 404
    )


def test_rejects_empty_code(auth_client: TestClient) -> None:
    response = submit(auth_client, code="   \n  ")

    assert response.status_code == 422
    assert "Code must not be empty" in response.text


def test_rejects_unsupported_language(auth_client: TestClient) -> None:
    response = submit(auth_client, language="brainfuck")

    assert response.status_code == 422
    assert "Unsupported language" in response.text


def test_rejects_oversized_code(auth_client: TestClient) -> None:
    oversized = "x" * (settings.max_code_length + 1)

    response = submit(auth_client, code=oversized)

    assert response.status_code == 413
    assert "maximum length" in response.json()["detail"]


def test_history_returns_newest_first_with_pagination(auth_client: TestClient) -> None:
    first = submit(auth_client, filename="first.py").json()
    time.sleep(0.01)
    second = submit(auth_client, filename="second.py", language="javascript").json()

    response = auth_client.get("/api/reviews")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]

    page = auth_client.get("/api/reviews", params={"limit": 1, "offset": 0}).json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == second["id"]

    filtered = auth_client.get("/api/reviews", params={"language": "python"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == first["id"]


def test_history_rejects_invalid_pagination(auth_client: TestClient) -> None:
    assert auth_client.get("/api/reviews", params={"limit": 0}).status_code == 422
    assert auth_client.get("/api/reviews", params={"offset": -1}).status_code == 422


def test_unknown_review_returns_404(auth_client: TestClient) -> None:
    response = auth_client.get("/api/reviews/rev_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found."


def test_filename_is_reduced_to_a_basename(auth_client: TestClient) -> None:
    response = submit(auth_client, filename="../../etc/passwd")

    assert response.status_code == 201
    assert response.json()["filename"] == "passwd"


def test_cors_allows_the_local_frontend(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    preflight = client.options(
        "/api/review",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
