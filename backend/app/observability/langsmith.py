"""Opt-in LangSmith tracing for provider calls."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from typing import Any

from app.observability.context import get_trace_id

try:
    from langsmith import trace as _trace
except ImportError:  # pragma: no cover - optional dependency before install
    _trace = None


def langsmith_tracing_enabled() -> bool:
    """Return whether tracing is explicitly enabled and configured."""

    enabled = os.getenv("LANGSMITH_TRACING", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    return enabled and bool(os.getenv("LANGSMITH_API_KEY", "").strip()) and _trace is not None


@contextmanager
def trace_llm_call(
    *,
    name: str,
    model: str,
    messages: list[dict[str, str]],
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Iterator[Any | None]:
    """Create an LLM span only when opt-in tracing is enabled.

    Tracing setup is isolated from the provider path. A missing key or SDK
    never prevents the local model request from running.
    """

    if not langsmith_tracing_enabled():
        yield None
        return

    try:
        trace_context = _trace(  # type: ignore[misc]
            name=name,
            run_type="llm",
            inputs={"model": model, "messages": messages},
            metadata={**(metadata or {}), "trace_id": get_trace_id()},
            tags=tags or [],
        )
    except Exception:
        # A telemetry configuration/network error must not hide the model call.
        yield None
        return

    with trace_context as run:
        yield run


def finish_trace(run: Any | None, *, outputs: dict[str, Any] | None = None) -> None:
    """Attach provider output to an active span without affecting the request."""

    if run is None:
        return
    try:
        run.end(outputs=outputs or {})
    except Exception:
        # Observability must never become a runtime dependency of chat.
        return


@contextmanager
def trace_graph_node(
    *,
    name: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Iterator[Any | None]:
    """Create a privacy-safe chain span for one LangGraph node."""

    if not langsmith_tracing_enabled():
        yield None
        return

    try:
        trace_context = _trace(
            name=name,
            run_type="chain",
            inputs={"node": name},
            metadata={**(metadata or {}), "trace_id": get_trace_id()},
            tags=tags or ["langgraph"],
        )
    except Exception:
        yield None
        return

    with trace_context as run:
        yield run
