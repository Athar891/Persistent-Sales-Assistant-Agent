"""Structured JSON logging.

One handler under the ``sales_agent`` logger tree emits a JSON object per record. The
request middleware and the notifier attach their fields via ``extra={"json_fields": {...}}``.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

_STANDARD_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "json_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("sales_agent")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper() if level.upper() in _STANDARD_LEVELS else "INFO")
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
