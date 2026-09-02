from __future__ import annotations

import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import observability_context
from app.observability.logging import log_event
from app.observability.metrics import METRICS


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_UUID_PATH = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


def _request_header(scope: Scope, name: bytes) -> str | None:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == name:
            return raw_value.decode("latin-1")
    return None


def _normalized_path(path: str) -> str:
    return _UUID_PATH.sub("/{id}", path)


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_request_id = _request_header(scope, b"x-request-id")
        request_id = (
            supplied_request_id
            if supplied_request_id and _SAFE_ID.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        trace_id = uuid4().hex
        started = perf_counter()
        status_code = 500
        method = str(scope.get("method", "UNKNOWN"))
        path = _normalized_path(str(scope.get("path", "")))
        raised = False

        async def observed_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        with observability_context(request_id=request_id, trace_id=trace_id):
            try:
                await self.app(scope, receive, observed_send)
            except Exception as exc:
                raised = True
                METRICS.increment(
                    "http_requests_total",
                    method=method,
                    path=path,
                    status="500",
                )
                METRICS.increment(
                    "http_request_errors_total",
                    method=method,
                    path=path,
                    error_type=type(exc).__name__,
                )
                log_event(
                    "http_request_failed",
                    level=logging.ERROR,
                    method=method,
                    path=path,
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                raise
            finally:
                duration_ms = (perf_counter() - started) * 1000
                METRICS.observe(
                    "http_request_duration_ms",
                    duration_ms,
                    method=method,
                    path=path,
                    status=str(status_code),
                )
                if not raised:
                    METRICS.increment(
                        "http_requests_total",
                        method=method,
                        path=path,
                        status=str(status_code),
                    )
                log_event(
                    "http_request_completed",
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=round(duration_ms, 3),
                )
