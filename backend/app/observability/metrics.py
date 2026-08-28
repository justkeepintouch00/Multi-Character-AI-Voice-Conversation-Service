from __future__ import annotations

import json
import math
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import RLock
from typing import Any


LabelKey = tuple[tuple[str, str], ...]


def _labels(values: dict[str, object]) -> LabelKey:
    return tuple(sorted((key, str(value)) for key, value in values.items()))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = rank - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


class MetricRegistry:
    """Small in-process baseline registry.

    It intentionally has no external dependency. The JSON snapshot is useful for
    local optimization comparisons; a later OpenTelemetry/Prometheus exporter can
    consume the same metric names without changing business code.
    """

    def __init__(self, *, histogram_limit: int = 10_000) -> None:
        self._lock = RLock()
        self._counters: dict[tuple[str, LabelKey], float] = defaultdict(float)
        self._histograms: dict[tuple[str, LabelKey], deque[float]] = defaultdict(
            lambda: deque(maxlen=histogram_limit)
        )

    def increment(self, name: str, value: float = 1, **labels: object) -> None:
        with self._lock:
            self._counters[(name, _labels(labels))] += value

    def observe(self, name: str, value: float, **labels: object) -> None:
        with self._lock:
            self._histograms[(name, _labels(labels))].append(float(value))

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {
                    "name": name,
                    "labels": dict(label_key),
                    "value": round(value, 6),
                }
                for (name, label_key), value in sorted(self._counters.items())
            ]
            histograms = []
            for (name, label_key), samples in sorted(self._histograms.items()):
                values = list(samples)
                histograms.append(
                    {
                        "name": name,
                        "labels": dict(label_key),
                        "count": len(values),
                        "min": round(min(values), 3) if values else None,
                        "max": round(max(values), 3) if values else None,
                        "mean": round(sum(values) / len(values), 3) if values else None,
                        "p50": _percentile(values, 0.50),
                        "p95": _percentile(values, 0.95),
                        "p99": _percentile(values, 0.99),
                    }
                )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "process_scope": "single_process",
            "counters": counters,
            "histograms": histograms,
        }


METRICS = MetricRegistry()


def _configured_cost(
    provider: str, model: str
) -> tuple[float, float] | None:
    raw = os.getenv("OBSERVABILITY_LLM_COSTS_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    item = parsed.get(f"{provider}:{model}") if isinstance(parsed, dict) else None
    if not isinstance(item, dict):
        return None
    try:
        return float(item["input_per_million"]), float(item["output_per_million"])
    except (KeyError, TypeError, ValueError):
        return None


def record_llm_usage(provider: str, model: str, payload: object) -> None:
    if not isinstance(payload, dict):
        return
    input_tokens = payload.get("prompt_tokens", payload.get("input_tokens"))
    output_tokens = payload.get("completion_tokens", payload.get("output_tokens"))
    total_tokens = payload.get("total_tokens")
    if isinstance(input_tokens, (int, float)):
        METRICS.increment(
            "llm_tokens_total", input_tokens, provider=provider, model=model, type="input"
        )
    if isinstance(output_tokens, (int, float)):
        METRICS.increment(
            "llm_tokens_total", output_tokens, provider=provider, model=model, type="output"
        )
    if isinstance(total_tokens, (int, float)):
        METRICS.increment(
            "llm_tokens_total", total_tokens, provider=provider, model=model, type="total"
        )
    costs = _configured_cost(provider, model)
    if costs and isinstance(input_tokens, (int, float)) and isinstance(
        output_tokens, (int, float)
    ):
        estimated = (
            input_tokens * costs[0] + output_tokens * costs[1]
        ) / 1_000_000
        METRICS.increment(
            "llm_estimated_cost_total",
            estimated,
            provider=provider,
            model=model,
            currency="configured",
        )
