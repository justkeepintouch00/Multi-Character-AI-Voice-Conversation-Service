from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def get_job_id() -> str | None:
    return _job_id.get()


def get_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def observability_context(
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[None]:
    request_token = _request_id.set(request_id)
    job_token = _job_id.set(job_id)
    trace_token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(trace_token)
        _job_id.reset(job_token)
        _request_id.reset(request_token)
