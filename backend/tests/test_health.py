from fastapi.testclient import TestClient

from app.api.routes import health
from app.main import app


client = TestClient(app)


def test_service_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "character-companion-backend",
    }


def test_database_health_when_connected(monkeypatch) -> None:
    monkeypatch.setattr(health, "database_is_reachable", lambda: True)

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_database_health_when_disconnected(monkeypatch) -> None:
    monkeypatch.setattr(health, "database_is_reachable", lambda: False)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "disconnected"}


def test_provider_health_when_all_providers_are_configured(monkeypatch) -> None:
    monkeypatch.setattr(health, "get_groq_api_key", lambda: "groq-secret")
    monkeypatch.setattr(health, "get_typecast_api_key", lambda: "typecast-secret")

    response = client.get("/health/providers")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "groq": {"configured": True},
        "typecast": {"configured": True},
    }


def test_provider_health_does_not_expose_secrets(monkeypatch) -> None:
    monkeypatch.setattr(health, "get_groq_api_key", lambda: None)
    monkeypatch.setattr(health, "get_typecast_api_key", lambda: "typecast-secret")

    response = client.get("/health/providers")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "groq": {"configured": False},
        "typecast": {"configured": True},
    }
    assert "secret" not in response.text


def test_openapi_exposes_health_endpoints() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
    assert "/health/db" in response.json()["paths"]
    assert "/health/providers" in response.json()["paths"]
