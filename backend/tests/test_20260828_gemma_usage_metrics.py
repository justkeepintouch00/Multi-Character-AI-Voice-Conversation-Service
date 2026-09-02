from __future__ import annotations

import httpx

from app.observability.metrics import METRICS, record_llm_usage
from app.providers.gemma import GemmaSceneDirector


def test_gemma_sse_preserves_usage_for_metrics() -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"{}"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":5,"total_tokens":17}}\n\n'
        'data: [DONE]\n\n'
    )
    response = httpx.Response(
        200,
        text=body,
        headers={"content-type": "text/event-stream"},
    )

    payload = GemmaSceneDirector._decode_response(response)

    assert payload["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "total_tokens": 17,
    }


def test_record_llm_usage_exports_token_counters() -> None:
    METRICS.reset()
    record_llm_usage(
        "gemma4_e2b",
        "gemma4-e2b",
        {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    )
    counters = METRICS.snapshot()["counters"]
    assert any(
        item["name"] == "llm_tokens_total"
        and item["labels"]["type"] == "input"
        and item["value"] == 12
        for item in counters
    )