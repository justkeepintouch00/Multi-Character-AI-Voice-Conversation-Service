from app.observability.metrics import MetricRegistry
from app.observability.prometheus import prometheus_exposition


def test_prometheus_exposition_contains_counters_and_latency_quantiles() -> None:
    registry = MetricRegistry()
    registry.increment(
        "http_requests_total",
        method="GET",
        path='/api/v1/items/"quoted"',
        status="200",
    )
    for value in (10, 20, 30):
        registry.observe(
            "http_request_duration_ms",
            value,
            method="GET",
            path="/health",
            status="200",
        )

    output = prometheus_exposition(registry.snapshot())

    assert "# TYPE character_companion_http_requests_total counter" in output
    assert 'path="/api/v1/items/\\"quoted\\""' in output
    assert "# TYPE character_companion_http_request_duration_ms_p95 gauge" in output
    assert (
        'character_companion_http_request_duration_ms_p95'
        '{method="GET",path="/health",status="200"} 29'
    ) in output
