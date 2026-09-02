"""Structured, privacy-aware runtime observations for evaluation.

LangSmith remains the source for detailed LLM traces.  This module stores the
small, stable subset of facts needed to join a test case to its retrieval and
generation result even when tracing is disabled or retained elsewhere.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeObservation:
    """Facts observed during one evaluation/application run.

    IDs and decision metadata are intentionally stored instead of raw memory
    text.  This keeps the local result safe to share and lets the UI resolve
    authorized memory labels separately.
    """

    case_id: str | None = None
    trace_id: str | None = None
    langsmith_run_id: str | None = None
    retrieved_memory_ids: list[str] = field(default_factory=list)
    prompt_memory_ids: list[str] = field(default_factory=list)
    disclosed_memory_ids: list[str] = field(default_factory=list)
    acl_decisions: list[dict[str, Any]] = field(default_factory=list)
    stale_memory_ids: list[str] = field(default_factory=list)
    graph_paths: list[dict[str, Any]] = field(default_factory=list)
    context_input_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    prompt_version: str | None = None
    memory_schema_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable observations without raw memory content."""

        return asdict(self)


def merge_observation(
    current: RuntimeObservation | None,
    **updates: Any,
) -> RuntimeObservation:
    """Apply partial node updates while preserving earlier observations."""

    result = current or RuntimeObservation()
    for key, value in updates.items():
        if value is not None and hasattr(result, key):
            setattr(result, key, value)
    return result

