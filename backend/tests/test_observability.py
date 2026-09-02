from fastapi.testclient import TestClient

from app.main import app
from app.observability.metrics import METRICS, MetricRegistry


client = TestClient(app)


def test_metric_registry_calculates_percentiles() -> None:
    registry = MetricRegistry()
    for value in (10, 20, 30, 40, 50):
        registry.observe("latency_ms", value, route="test")

    histogram = registry.snapshot()["histograms"][0]

    assert histogram == {
        "name": "latency_ms",
        "labels": {"route": "test"},
        "count": 5,
        "min": 10.0,
        "max": 50.0,
        "mean": 30.0,
        "p50": 30.0,
        "p95": 48.0,
        "p99": 49.6,
    }


def test_request_id_is_propagated_and_health_request_is_measured() -> None:
    METRICS.reset()

    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"

    metrics_response = client.get("/api/v1/observability/metrics")
    assert metrics_response.status_code == 200
    snapshot = metrics_response.json()
    assert snapshot["process_scope"] == "single_process"
    assert any(
        item["name"] == "http_requests_total"
        and item["labels"] == {
            "method": "GET",
            "path": "/health",
            "status": "200",
        }
        and item["value"] == 1
        for item in snapshot["counters"]
    )
    assert any(
        item["name"] == "http_request_duration_ms"
        and item["labels"]["path"] == "/health"
        and item["count"] == 1
        for item in snapshot["histograms"]
    )


def test_invalid_request_id_is_replaced() -> None:
    response = client.get("/health", headers={"X-Request-ID": "invalid request id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid request id"
    assert len(response.headers["X-Request-ID"]) == 36
