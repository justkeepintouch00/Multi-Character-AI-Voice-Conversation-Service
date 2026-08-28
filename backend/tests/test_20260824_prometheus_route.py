from fastapi.testclient import TestClient

from app.main import app
from app.observability.metrics import METRICS


client = TestClient(app)


def test_prometheus_metrics_route() -> None:
    METRICS.reset()
    health_response = client.get("/health")
    assert health_response.status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "character_companion_http_requests_total" in response.text
    assert 'path="/health"' in response.text
