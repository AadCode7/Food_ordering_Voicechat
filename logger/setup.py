"""Structured JSON logging. Every line carries the request id and (when tracing) the trace id."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

from config import settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_ROOT = "foodbot"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        try:
            from opentelemetry import trace

            ctx = trace.get_current_span().get_span_context()
            if ctx and ctx.is_valid:
                payload["trace_id"] = format(ctx.trace_id, "032x")
        except Exception:  # telemetry is optional
            pass
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    root = logging.getLogger(_ROOT)
    if getattr(root, "_foodbot_ready", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    root.propagate = False
    root._foodbot_ready = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_ROOT}.{name}")


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **ctx) -> None:
    logger.log(level, event, extra={"ctx": ctx})
