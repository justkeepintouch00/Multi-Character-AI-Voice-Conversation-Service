from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.observability.context import get_job_id, get_request_id, get_trace_id


LOGGER_NAME = "character_companion"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "job_id": get_job_id(),
            "trace_id": get_trace_id(),
        }
        event_fields = getattr(record, "event_fields", None)
        if isinstance(event_fields, dict):
            payload.update(event_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if any(getattr(handler, "_character_companion_json", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._character_companion_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    logging.getLogger(LOGGER_NAME).log(
        level,
        event,
        extra={"event_fields": {"event": event, **fields}},
        exc_info=exc_info,
    )
