from __future__ import annotations

import math
import re
from typing import Any


_METRIC_NAME = re.compile(r"[^a-zA-Z0-9_:]")
_PREFIX = "character_companion_"


def _metric_name(value: object) -> str:
    normalized = _METRIC_NAME.sub("_", str(value))
    if not normalized or normalized[0].isdigit():
        normalized = f"metric_{normalized}"
    return f"{_PREFIX}{normalized}"


def _escape_label(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _labels(values: dict[str, object]) -> str:
    if not values:
        return ""
    rendered = ",".join(
        f'{_METRIC_NAME.sub("_", str(key))}="{_escape_label(value)}"'
        for key, value in sorted(values.items())
    )
    return f"{{{rendered}}}"


def _number(value: object) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return format(numeric, ".15g")


def prometheus_exposition(snapshot: dict[str, Any]) -> str:
    """Render a MetricRegistry snapshot using Prometheus text format 0.0.4.

    Counters remain counters. Reservoir statistics are exported as gauges because
    their p50/p95/p99 values are calculated over the process-local recent-sample
    reservoir rather than Prometheus histogram buckets.
    """

    lines = [
        "# HELP character_companion_observability_info Process-local registry metadata.",
        "# TYPE character_companion_observability_info gauge",
        (
            "character_companion_observability_info"
            f'{{process_scope="{_escape_label(snapshot.get("process_scope", "unknown"))}"}} 1'
        ),
    ]

    declared: set[str] = set()
    for item in snapshot.get("counters", []):
        if not isinstance(item, dict):
            continue
        name = _metric_name(item.get("name", "unknown_counter"))
        value = _number(item.get("value"))
        labels = item.get("labels")
        if value is None or not isinstance(labels, dict):
            continue
        if name not in declared:
            lines.extend((f"# TYPE {name} counter",))
            declared.add(name)
        lines.append(f"{name}{_labels(labels)} {value}")

    fields = ("count", "min", "max", "mean", "p50", "p95", "p99")
    for item in snapshot.get("histograms", []):
        if not isinstance(item, dict):
            continue
        base_name = _metric_name(item.get("name", "unknown_distribution"))
        labels = item.get("labels")
        if not isinstance(labels, dict):
            continue
        for field in fields:
            value = _number(item.get(field))
            if value is None:
                continue
            name = f"{base_name}_{field}"
            if name not in declared:
                lines.append(f"# TYPE {name} gauge")
                declared.add(name)
            lines.append(f"{name}{_labels(labels)} {value}")

    return "\n".join(lines) + "\n"
